from fabric import api
from devops.ci import install

def build_svarog_streamer():
    api.local("python3 deb_package/svarog-streamer.py")
    api.local("mkdir -p dist")
    api.local("mv deb_package/build/svarog-streamer*/*.deb dist")
    install.sign_debs('dist')


def download_svarog(link, token):
    api.local('curl --header "PRIVATE-TOKEN: {}" -L {}  --output svarog.zip'.format(token, link))
