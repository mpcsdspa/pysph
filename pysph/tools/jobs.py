# Standard libraray imports
from __future__ import print_function

from collections import deque
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

# External module imports.
import psutil


class Job(object):
    def __init__(self, command, output_dir, n_core=1, n_thread=1, env=None):
        """Constructor

        Note that `n_core` is used to schedule a task on a machine which has
        that many free cores. `n_thread` is used to set the `OMP_NUM_THREADS`.

        """
        if not isinstance(command, (list, tuple)):
            command = shlex.split(command)
        args = []
        for x in command:
            if os.path.basename(x) == 'python':
                args.append(sys.executable)
            else:
                args.append(x)
        self.command = args
        self._given_env = env
        self.env = dict(env) if env is not None else dict(os.environ)
        self.env['OMP_NUM_THREADS'] = str(n_thread)
        self.n_core = n_core
        self.n_thread = n_thread
        self.output_dir = output_dir
        self.output_already_exists = os.path.exists(self.output_dir)
        self.stderr = os.path.join(self.output_dir, 'stderr.txt')
        self.stdout = os.path.join(self.output_dir, 'stdout.txt')
        self.proc = None

    def to_dict(self):
        state = dict()
        for key in ('command', 'output_dir', 'n_core', 'n_thread'):
            state[key] = getattr(self, key)
        state['env'] = self._given_env
        return state

    def pretty_command(self):
        return ' '.join(self.command)

    def get_stderr(self):
        return open(self.stderr).read()

    def get_stdout(self):
        return open(self.stdout).read()

    def run(self):
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        stdout = open(self.stdout, 'wb')
        stderr = open(self.stderr, 'wb')
        self.proc = subprocess.Popen(
            self.command, stdout=stdout, stderr=stderr, env=self.env
        )
        self.proc.poll()

    def status(self):
        if self.proc is None:
            if os.path.exists(self.stdout):
                return 'done'
            else:
                return 'not started'
        if self.proc is not None:
            self.proc.poll()
            retcode = self.proc.returncode
            if retcode is not None:
                if retcode > 0:
                    return 'error'
                else:
                    return 'done'
            else:
                return 'running'

    def clean(self, force=False):
        if self.output_already_exists and not force:
            if os.path.exists(self.stdout):
                os.remove(self.stdout)
                os.remove(self.stderr)
        elif os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)


def free_cores():
    free = (1.0 - psutil.cpu_percent(interval=0.5)/100.)
    ncore = free*psutil.cpu_count(logical=False)
    return round(ncore, 0)


############################################
# This class is meant to be used by execnet alone.
class _RemoteManager(object):
    def __init__(self):
        self.jobs = dict()
        self.job_count = 0
        self._setup_path()

    def _setup_path(self):
        py_dir = os.path.dirname(sys.executable)
        env_path = os.environ.get('PATH').split(os.pathsep)
        if py_dir not in env_path:
            env_path.insert(0, py_dir)
            os.environ['PATH'] = os.pathsep.join(env_path)

    def run(self, job_data):
        job = Job(**job_data)
        job.run()
        ret_val = self.job_count
        self.jobs[ret_val] = job
        self.job_count += 1
        return ret_val

    def status(self, job_id):
        if job_id in self.jobs:
            return self.jobs[job_id].status()
        else:
            return 'invalid job id %d' % job_id

    def clean(self, job_id, force=False):
        if job_id in self.jobs:
            return self.jobs[job_id].clean(force)
        else:
            return 'invalid job id %d' % job_id

    def get_stdout(self, job_id):
        return self.jobs[job_id].get_stdout()

    def get_stderr(self, job_id):
        return self.jobs[job_id].get_stderr()


def serve(channel):
    """Serve the remote manager via execnet.
    """
    manager = _RemoteManager()
    while True:
        msg, data = channel.receive()
        if msg == 'free_cores':
            channel.send(free_cores())
        else:
            channel.send(getattr(manager, msg)(*data))
############################################


class Worker(object):
    def __init__(self):
        self.jobs = dict()
        self.running_jobs = set()

    def _check_running_jobs(self):
        for i in self.running_jobs.copy():
            self.status(i)

    def free_cores(self):
        return free_cores()

    def can_run(self, n_core):
        """Returns True if the worker can run a job with the required cores.
        """
        if n_core == 0:
            return True
        free = self.free_cores()
        result = False
        if free >= n_core:
            self._check_running_jobs()
            jobs = self.jobs
            n_cores_used = sum(
                [jobs[i].n_core for i in self.running_jobs]
            )
            if (free - n_cores_used) >= n_core:
                result = True
        return result

    def run(self, job):
        """Runs the job and returns a JobProxy for the job."""
        raise NotImplementedError()

    def status(self, job_id):
        """Returns status of the job."""
        raise NotImplementedError()

    def copy_output(self, job_id, dest):
        raise NotImplementedError()

    def clean(self, job_id, force=False):
        raise NotImplementedError()

    def get_stdout(self, job_id):
        raise NotImplementedError()

    def get_stderr(self, job_id):
        raise NotImplementedError()


class JobProxy(object):
    def __init__(self, worker, job_id, job):
        self.worker = worker
        self.job_id = job_id
        self.job = job

    def free_cores(self):
        return self.worker.free_cores()

    def run(self):
        print("JobProxy cannot be run")

    def status(self):
        return self.worker.status(self.job_id)

    def copy_output(self, dest):
        return self.worker.copy_output(self.job_id, dest)

    def clean(self, force=False):
        return self.worker.clean(self.job_id, force)

    def get_stdout(self):
        return self.worker.get_stdout(self.job_id)

    def get_stderr(self):
        return self.worker.get_stderr(self.job_id)


class LocalWorker(Worker):
    def __init__(self):
        super(LocalWorker, self).__init__()
        self.host = 'localhost'
        self.job_count = 0

    def get_config(self):
        return dict(host='localhost')

    def run(self, job):
        count = self.job_count
        print("Running %s" % job.pretty_command())
        self.jobs[count] = job
        self.running_jobs.add(count)
        job.run()
        self.job_count += 1
        return JobProxy(self, count, job)

    def status(self, job_id):
        s = self.jobs[job_id].status()
        rj = self.running_jobs
        if s != 'running':
            rj.discard(job_id)
        return s

    def copy_output(self, job_id, dest):
        return

    def clean(self, job_id, force=False):
        if force:
            self.jobs[job_id].clean(force)

    def get_stdout(self, job_id):
        return self.jobs[job_id].get_stdout()

    def get_stderr(self, job_id):
        return self.jobs[job_id].get_stderr()


class RemoteWorker(Worker):
    def __init__(self, host, python, chdir=None, testing=False):
        super(RemoteWorker, self).__init__()
        self.host = host
        self.python = python
        self.chdir = chdir
        self.testing = testing
        if testing:
            spec = 'popen//python={python}'.format(python=python)
        else:
            spec = 'ssh={host}//python={python}'.format(
                host=host, python=python
            )
        if chdir is not None:
            spec += '//chdir={chdir}'.format(chdir=chdir)

        import execnet
        self.gw = execnet.makegateway(spec)
        self.channel = self.gw.remote_exec(
            "from pysph.tools import jobs; jobs.serve(channel)"
        )

    def get_config(self):
        return dict(host=self.host, python=self.python, chdir=self.chdir)

    def _call_remote(self, method, *data):
        ch = self.channel
        ch.send((method, data))
        return ch.receive()

    def free_cores(self):
        return self._call_remote('free_cores', None)

    def run(self, job):
        print("Running %s" % job.pretty_command())
        job_id = self._call_remote('run', job.to_dict())
        self.jobs[job_id] = job
        self.running_jobs.add(job_id)
        return JobProxy(self, job_id, job)

    def status(self, job_id):
        s = self._call_remote('status', job_id)
        rj = self.running_jobs
        if s != 'running':
            rj.discard(job_id)
        return s

    def copy_output(self, job_id, dest):
        job = self.jobs[job_id]
        if self.testing:
            src = os.path.join(self.chdir, job.output_dir)
            real_dest = os.path.join(dest, job.output_dir)
            args = [
                sys.executable, '-c',
                'import sys,shutil; shutil.copytree(sys.argv[1], sys.argv[2])',
                src, real_dest
            ]
        else:
            src = '{host}:{path}'.format(
                host=self.host, path=os.path.join(self.chdir, job.output_dir)
            )
            real_dest = os.path.join(dest, os.path.dirname(job.output_dir))
            args = ['scp', '-qr', src, real_dest]

        print("\n" + " ".join(args))
        proc = subprocess.Popen(args)
        return proc

    def clean(self, job_id, force=False):
        return self._call_remote('clean', job_id, force)

    def get_stdout(self, job_id):
        return self._call_remote('get_stdout', job_id)

    def get_stderr(self, job_id):
        return self._call_remote('get_stderr', job_id)


class Scheduler(object):
    def __init__(self, root='.', worker_config=()):
        self.workers = deque()
        self.worker_config = list(worker_config)
        self.root = os.path.abspath(os.path.expanduser(root))
        self._completed_jobs = []
        self.jobs = []

    def _create_worker(self):
        conf = self.worker_config[len(self.workers)]
        host = conf.get('host')
        print("Starting worker on %s." % host)
        if host == 'localhost':
            w = LocalWorker()
        else:
            w = RemoteWorker(**conf)
        self.workers.append(w)
        return w

    def _get_active_workers(self):
        completed = []
        workers = set()
        for job in self.jobs:
            if job.status() in ['error', 'done']:
                completed.append(job)
            else:
                workers.add(job.worker.host)

        for job in completed:
            self.jobs.remove(job)
            self._completed_jobs.append(job)

        return workers

    def _rotate_existing_workers(self):
        worker = self.workers[0]
        self.workers.rotate(-1)
        return worker

    def _get_worker(self, n_core):
        n_configs = len(self.worker_config)
        n_running = len(self.workers)
        if n_running == n_configs:
            worker = self._rotate_existing_workers()
        else:
            active_workers = self._get_active_workers()
            if n_running > len(active_workers):
                for w in self.workers:
                    if (w.host not in active_workers) and \
                       w.can_run(n_core):
                        worker = w
                        break
                else:
                    worker = self._create_worker()
            else:
                worker = self._create_worker()
        return worker

    def save(self, fname):
        config = dict(root=self.root)
        config['workers'] = self.worker_config
        json.dump(config, open(fname, 'w'), indent=2)

    def load(self, fname):
        config = json.load(open(fname))
        self.root = config.get('root')
        self.worker_config = config.get('workers')

    def add_worker(self, conf):
        self.worker_config.append(conf)

    def submit(self, job, wait=5):
        proxy = None
        slept = False
        while proxy is None:
            for i in range(len(self.worker_config)):
                worker = self._get_worker(job.n_core)
                if worker.can_run(job.n_core):
                    if slept:
                        print()
                        slept = False
                    print("Job run by %s" % worker.host)
                    proxy = worker.run(job)
                    self.jobs.append(proxy)
                    break
            else:
                time.sleep(wait)
                slept = True
                print("\rWaiting for free worker ...", end='')
                sys.stdout.flush()
        return proxy
