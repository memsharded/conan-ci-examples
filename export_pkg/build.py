"""
Needs 1 Artifactory repo in: http://localhost:8081/artifactory/api/conan/ci-master
"""

import json
import os

from utils.ci import CI
from utils.user import User
from utils.utils import setenv, chdir, load, save

User.base_folder = os.path.realpath(os.path.dirname(__file__))
CI.base_folder = os.path.realpath(os.path.dirname(__file__))
ci_server = CI()


def package_pipeline(ci, repository, branch, upload=None, lockfile=None):
    job, job_folder = ci.new_job()
    job_folder += "_pkg"
    cache_folder = os.path.join(job_folder, "cache")
    os.makedirs(cache_folder, exist_ok=True)
    with setenv("CONAN_USER_HOME", cache_folder):
        ci.run("conan config set general.revisions_enabled=True")
        ci.run("conan config set general.default_package_id_mode=recipe_revision_mode")
        ci.run("conan remote remove conan-center")
        ci.run("conan remote add master http://localhost:8081/artifactory/api/conan/ci-master -f")
        ci.run("conan user admin -p=password -r=master")
        with chdir(job_folder):
            ci.run("git clone %s" % repository)
            repo_folder = os.path.basename(repository)
            with chdir(repo_folder):
                ci.run("git checkout %s" % branch)
                os.makedirs("build")
                with chdir("build"):
                    # This build is external to Conan
                    if lockfile:
                        save("conan.lock", lockfile)
                    else:
                        ci.run("conan graph lock ..")
                    ci.run("conan install .. --lockfile")
                    ci.run('cmake ../src -G "Visual Studio 15 Win64"')
                    ci.run('cmake --build . --config Release')
                    ci.run("conan export-pkg .. user/testing --ignore-dirty --lockfile")
        if upload:
            ci.run("conan upload * -r=%s --all --confirm" % upload)


def product_pipeline(ci):
    job, job_folder = ci.new_job()
    job_folder += "_product"
    cache_folder = os.path.join(job_folder, "cache")
    os.makedirs(cache_folder, exist_ok=True)
    with setenv("CONAN_USER_HOME", cache_folder):
        ci.run("conan config set general.revisions_enabled=True")
        ci.run("conan config set general.default_package_id_mode=recipe_revision_mode")
        ci.run("conan remote remove conan-center")
        ci.run("conan remote add master http://localhost:8081/artifactory/api/conan/ci-master -f")
        ci.run("conan user admin -p=password -r=master")
        with chdir(job_folder):
            ci.run("conan graph lock app/[~1.0]@user/testing --build")  # Always all build, as soon as we export, it will change
            lockfile = load("conan.lock")
            ci.run("conan graph build-order . --build=missing --json=build-order.json")
            build_order = json.loads(load("build-order.json"))
            print("*********** BUILD-ORDER *******************\n%s" % build_order)
            for level_to_build in build_order:
                for to_build in level_to_build:
                    ref = to_build[1].split(":")[0]
                    print("Building ", ref)
                    ci.run("conan inspect %s -a=scm --json=scm.json" % ref)
                    scm = json.loads(load("scm.json"))["scm"]
                    os.remove("scm.json")
                    url = scm["url"]
                    revision = scm["revision"]
                    package_pipeline(ci, url, branch=revision, lockfile=lockfile, upload="master")

            ci.run("conan install app/[~1.0]@user/testing --lockfile -g=deploy")
            ci.run(r".\app\bin\main_app.exe")


# Create 3 repos in the server
git_server = User("git_server")
repos_urls = {}
for pkg in ("hello", "chat", "app"):
    git_server.cd(pkg)
    repos_urls[pkg] = git_server.current_folder
    git_server.git_init(readme=True)
    git_server.run("git config --bool core.bare true")

# User bob puts some code and create packages
bob = User("bob")
for pkg in ("hello", "chat", "app"):
    repo = repos_urls[pkg]
    bob.git_clone(repo)
    bob.cd(pkg)
    bob.copy_code("sources/%s" % pkg)
    bob.git_commit()
    bob.git_push()
    # Every push fires a package pipeline
    package_pipeline(ci_server, repo, branch="master", upload="master")


# User Alice does some changes and push
alice = User("alice")
pkg = "hello"
repo = repos_urls[pkg]
alice.git_clone(repo)
alice.cd(pkg)
alice.edit("src/hello.cpp", "World", "Moon")
alice.git_commit()
alice.git_push()
package_pipeline(ci_server, repo, branch="master", upload="master")
product_pipeline(ci_server)
