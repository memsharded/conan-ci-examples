import os

from utils.utils import rmdir


class CI(object):
    base_folder = None

    def __init__(self, product=None):
        self.ci_folder = os.path.join(self.base_folder, "tmp", "ci")
        rmdir(self.ci_folder)
        self.product = product
        self._build_counter = 0

    def new_job(self):
        job = self._build_counter
        self._build_counter += 1
        job_folder = os.path.join(self.ci_folder, "build%s" % job)
        return job, job_folder

    def run(self, cmd):
        print("RUNNING (CI): %s" % cmd)
        ret = os.system(cmd)
        if ret != 0:
            raise Exception("Command failed: %s" % cmd)
