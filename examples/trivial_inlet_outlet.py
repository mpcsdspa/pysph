"""A trivial example to demonstrate the inlet and outlet feature.
"""

import numpy as np

from pysph.base.kernels import CubicSpline
from pysph.base.utils import get_particle_array
from pysph.solver.application import Application
from pysph.solver.solver import Solver
from pysph.sph.integrator import PECIntegrator
from pysph.sph.simple_inlet_outlet import SimpleInlet, SimpleOutlet
from pysph.sph.integrator_step import InletOutletStep

def create_particles():
    # Note that you need to create the inlet and outlet arrays in this method.

    # Initially fluid has no particles -- these are generated by the outlet.
    fluid = get_particle_array(name='fluid')

    outlet = get_particle_array(name='outlet')

    # Setup the inlet particle array with just the particles we need at the
    # exit plane which is always the right side of the box defining the inlet.
    dx = 0.1
    y = np.linspace(0, 1, 11)
    x = np.zeros_like(y)
    m = np.ones_like(x)*dx
    h = np.ones_like(x)*dx*1.5
    rho = np.ones_like(x)
    # Remember to set u otherwise the inlet particles won't move.
    u = np.ones_like(x)*0.25

    inlet = get_particle_array(name='inlet', x=x, y=y, m=m, h=h, u=u, rho=rho)

    return [inlet, fluid, outlet]

def create_inlet_outlet(particle_arrays):
    # particle_arrays is a dict {name: particle_array}
    fluid_pa = particle_arrays['fluid']
    inlet_pa = particle_arrays['inlet']
    outlet_pa = particle_arrays['outlet']

    inlet = SimpleInlet(
        inlet_pa, fluid_pa, spacing=0.1, n=5, axis='x', xmin=-0.4, xmax=0.0,
        ymin=0.0, ymax=1.0
    )
    outlet = SimpleOutlet(
        outlet_pa, fluid_pa, xmin=0.5, xmax=1.0, ymin=0.0, ymax=1.0
    )
    return [inlet, outlet]


app = Application()
kernel = CubicSpline(dim=2)
integrator = PECIntegrator(
    fluid=InletOutletStep(), inlet=InletOutletStep(), outlet=InletOutletStep()
)

dt = 1e-2
tf = 5

solver = Solver(
    kernel=kernel, dim=2, integrator=integrator, dt=dt, tf=tf,
    adaptive_timestep=False
)

app.setup(
    solver=solver, equations=[], particle_factory=create_particles,
    inlet_outlet_factory=create_inlet_outlet
)

app.run()
