""" Dumps VTK output files

It takes a hdf or npz file as an input and output vtu file.
"""
from pysph import has_tvtk, has_pyvisfile
from pysph.solver.output import Output, load
import numpy as np
import argparse
import sys
import os


class VTKOutput(Output):

    def __init__(self, scalars=None, **kwargs):
        self.set_output_scalar(scalars)
        self.set_output_vector(**kwargs)
        super(VTKOutput, self).__init__(True)

    def set_output_vector(self, **kwargs):
        """
        Set the vector to dump in VTK output

        Parameter
        ----------

        kwargs:
            Vectors to dump
            Example V=['u', 'v', 'z']
        """

        self.vectors = {}
        for name, vector in kwargs.items():
            assert (len(vector) is 3)
            self.vectors[name] = vector

    def set_output_scalar(self, scalars=None):
        """
        Set the scalars to dump in VTK output

        Parameter
        ---------
        scalar_array: list
            The set of properties to dump
        """
        if scalars is None:
            self.scalars = []
        else:
            self.scalars = scalars

    def _get_scalars(self, arrays):
        scalars = []
        for prop_name in self.scalars:
            scalars.append((prop_name, arrays[prop_name]))
        return scalars

    def _get_vectors(self, arrays):
        vectors = []
        for prop_name, prop_list in self.vectors.items():
            vec = np.array([arrays[prop_list[0]], arrays[prop_list[1]],
                            arrays[prop_list[2]]])
            data = (prop_name, vec)
            vectors.append(data)
        return vectors

    def _dump(self, filename):
        for ptype, pdata in self.all_array_data.items():
            self._setup_data(pdata)
            self._dump_arrays(filename + '_' + ptype)

    def _setup_data(self, arrays):
        self.numPoints = arrays['x'].size
        self.points = np.array([arrays['x'], arrays['y'],
                                arrays['z']])
        self.data = []
        self.data.extend(self._get_scalars(arrays))
        self.data.extend(self._get_vectors(arrays))


class PyVisFileOutput(VTKOutput):

    def _dump_arrays(self, filename):
        from pyvisfile.vtk import (UnstructuredGrid, DataArray,
                                   AppendedDataXMLGenerator, VTK_VERTEX)
        n = self.numPoints
        da = DataArray("points", self.points)
        grid = UnstructuredGrid((n, da), cells=np.arange(n),
                                cell_types=np.asarray([VTK_VERTEX] * n))
        for name, field in self.data:
            da = DataArray(name, field)
            grid.add_pointdata(da)
        with open(filename + '.vtu', "w") as f:
            AppendedDataXMLGenerator(None)(grid).write(f)


class TVTKOutput(VTKOutput):
    def _dump_arrays(self, filename):
        from tvtk.api import tvtk
        n = self.numPoints
        cells = np.arange(n)
        cells.shape = (n, 1)
        cell_type = tvtk.Vertex().cell_type
        ug = tvtk.UnstructuredGrid(points=self.points.transpose())
        ug.set_cells(cell_type, cells)
        from mayavi.core.dataset_manager import DatasetManager
        dsm = DatasetManager(dataset=ug)
        for name, feild in self.data:
            dsm.add_array(feild.transpose(), name)
            dsm.activate(name)
        from tvtk.api import write_data
        write_data(ug, filename)


def dump_vtk(filename, particles, scalars=None, **kwargs):
    if has_pyvisfile():
        output = PyVisFileOutput(scalars, **kwargs)
    elif has_tvtk():
        output = TVTKOutput(scalars, **kwargs)
    else:
        msg = 'TVTK and pyvisfile Not present'
        raise ImportError(msg)
    output.dump(filename, particles, {})


def run(options):
    data = load(str(options.inputfile))
    particles = []
    for ptype, pdata in data['arrays'].items():
        particles.append(pdata)
    filename = os.path.splitext(options.inputfile)[0]
    if options.outdir is not None:
        filename = options.os_dir + os.path.split(filename)[1]
    dump_vtk(filename, particles, scalars=options.scalars,
             V=['u', 'v', 'w'])


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog='dump_vtk', description=__doc__, add_help=False
    )

    parser.add_argument(
        "-h", "--help", action="store_true", default=False, dest="help",
        help="show this help message and exit"
    )

    parser.add_argument(
        "-s", "--scalars",  metavar="scalars", type=str, nargs='+', default=[],
        help="scalars variables to dump in VTK output"
    )

    parser.add_argument(
        "-od", "--outdir",  metavar="outdir", type=str, default=None,
        help="Directory to output VTK files"
    )

    parser.add_argument(
        "-if", "--inputfile", metavar="inputfile", type=str, required=True,
        help="input file to take (hdf5 or npz)"
    )

    if len(argv) > 0 and argv[0] in ['-h', '--help']:
        parser.print_help()
        sys.exit()

    options, extra = parser.parse_known_args(argv)
    run(options)

if __name__ == '__main__':
    main()
