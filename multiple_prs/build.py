"""
Needs 1 Artifactory repo
"""

import json
import os

from utils.ci import CI
from utils.user import User
from utils.utils import setenv, chdir, load, save

User.base_folder = os.path.realpath(os.path.dirname(__file__))
CI.base_folder = os.path.realpath(os.path.dirname(__file__))
ci_server = CI()
artifactory = "http://localhost:8081/artifactory/api/conan/conan-local"
artifactory_user = "admin"
artifactory_passwd = "Patata!12"


def package_pipeline(ci, repository, branch, upload=None, lockfile=None):
    job, job_folder = ci.new_job()
    job_folder += "_pkg"
    cache_folder = os.path.join(job_folder, "cache")
    os.makedirs(cache_folder, exist_ok=True)
    with setenv("CONAN_USER_HOME", cache_folder):
        ci.run("conan config set general.revisions_enabled=True")
        ci.run("conan config set general.default_package_id_mode=recipe_revision_mode")
        ci.run("conan remote remove conan-center")
        ci.run("conan remote add master {} -f".format(artifactory))
        ci.run("conan user {} -p={} -r=master".format(artifactory_user, artifactory_passwd))
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
                        ci.run("conan lock create ../conanfile.py --user=user --channel=testing "
                               "-s compiler.version=15 --lockfile-out=conan.lock")
                    ci.run("conan install .. user/testing --lockfile=conan.lock")
                    ci.run('cmake ../src -G "Visual Studio 15 Win64"')
                    ci.run('cmake --build . --config Release')
                    ci.run("conan export-pkg .. user/testing --ignore-dirty --lockfile=conan.lock "
                           "--lockfile-out=conan_new.lock")
                    new_lockfile = load("conan_new.lock")
        if upload:
            ci.run("conan upload * -r=%s --all --confirm" % upload)
        return new_lockfile


def product_pipeline(ci):
    job, job_folder = ci.new_job()
    job_folder += "_product"
    cache_folder = os.path.join(job_folder, "cache")
    os.makedirs(cache_folder, exist_ok=True)
    with setenv("CONAN_USER_HOME", cache_folder):
        ci.run("conan config set general.revisions_enabled=True")
        ci.run("conan config set general.default_package_id_mode=recipe_revision_mode")
        ci.run("conan remote remove conan-center")
        ci.run("conan remote add master {} -f".format(artifactory))
        ci.run("conan user {} -p={} -r=master".format(artifactory_user, artifactory_passwd))
        with chdir(job_folder):
            ci.run("conan lock create --reference=app/[~1.0]@user/testing -s compiler.version=15 --build=missing")
            lockfile = load("conan.lock")
            ci.run("conan lock build-order conan.lock --json=build-order.json")
            build_order = json.loads(load("build-order.json"))
            print("*********** BUILD-ORDER *******************\n%s" % build_order)
            for level_to_build in build_order:
                for to_build in level_to_build:
                    ref = to_build[0]
                    print("Building ", ref)
                    ci.run("conan inspect %s -a=scm --json=scm.json" % ref)
                    scm = json.loads(load("scm.json"))["scm"]
                    os.remove("scm.json")
                    url = scm["url"]
                    revision = scm["revision"]
                    new_lockfile = package_pipeline(ci, url, branch=revision,
                                                    lockfile=lockfile, upload="master")
                    save("conan_new.lock", new_lockfile)
                    ci.run("conan lock update conan.lock conan_new.lock")

            ci.run("conan install app/1.0@user/testing --lockfile=conan.lock -g=deploy")
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
alice.edit("src/hello.cpp", "hello(){", "hello(std::string msg){std::cout<<msg<<std::endl;")
alice.edit("src/hello.h", "#pragma once", "#pragma once\n#include <string>")
alice.edit("src/hello.h", "hello()", "hello(std::string msg)")
alice.git_commit()
alice.git_push()

pkg = "chat"
repo = repos_urls[pkg]
alice.git_clone(repo)
alice.cd(pkg)
alice.edit("stc/chat.cpp", "hello()", 'hello("MyParameter!")')
alice.git_commit()
alice.git_push()

joint_pipeline(ci_server, ["hello", "chat"], branch="parameter", upload="master")
