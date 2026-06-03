#!/bin/bash -x
PYTHON_VERSION="{{python_version}}"
PYTHON_BASEDIR="{{python_basedir}}"

## Fail on error.
set -e

{% if build_deps %}
# Refresh repositories list to avoid problems with too old databases.
apt-get update
# Install build dependencies.
apt-get install -y {{build_deps|join(' ')}}
{% endif %}

{% if compile_python %}
# Download and compile what is going to be the Python we are going to use
# as our portable python environment.
    cd /var/tmp
    curl -O https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz
    tar xzvf Python-$PYTHON_VERSION.tgz
    cd Python-$PYTHON_VERSION
    ./configure --prefix=$PYTHON_BASEDIR --with-ensurepip=install
    make && make install
{% endif %}

# Create temporary folder to place our application files.
if [ ! -d {{package_tmp_root}} ]; then
    mkdir -p {{package_tmp_root}}
fi

cd {{package_tmp_root}}

{% if source.type == 'git' %}
    # Place application files inside temporary folder after dowloading it from
    # git repository.
    git clone {{source.uri}}
    cd {{project_root}}
    git checkout {{source.branch}}

{% elif source.type in ['directory', 'git_directory'] %}
    # Place application files inside temporary folder after copying it from
    # local folder.
    cp -r {{shared_dir}}/{{scratch_folder_name}}/{{project_root}} {{app}}
    cd {{app}}

    {% if source.type == 'git_directory' %}
        git checkout {{source.branch}}
    {% endif %}

{% else %}

    echo "invalid source type, exiting."
    exit 1

{% endif %}

{% if use_local_pip_conf %}
    cp -r {{scratch_dir}}/.pip ~
{% endif %}

{% if working_dir %}
    # When working_dir is set, assume that is the base and remove the rest
    mv {{working_dir}} {{package_tmp_root}} && rm -rf {{package_tmp_root}}/{{project_root}}
    cd {{package_tmp_root}}/{{working_dir}}

    # Reset project_root.
    {% set project_root = working_dir %}
{% endif %}

# We are going to remove any traces of a previous virtualenv that we could
# have imported with project, to keep things clean.
## TODO: Give it a second thought. It's odd to have virtualenv folders in a
## code repository. Whereas you may have a folder called "lib" or "bin" that
## you may want to package but it doesn't come from a virtualenv. Maybe we
## should remove next line in a further revision.
# rm -rf bin include lib local

# To install our application and dependencies inside our portable python
# environment we have to run setup.py and download from Pypi using our
# portable python environment "python" and "pip" executables.
if [[ ${PYTHON_VERSION:0:1} == "2" ]]; then
    PYTHON_BIN="$PYTHON_BASEDIR/bin/python"
    PIP_BIN="$PYTHON_BASEDIR/bin/pip"
    $PYTHON_BIN -m ensurepip
else
    PYTHON_BIN="$PYTHON_BASEDIR/bin/python3"
    PIP_BIN="$PYTHON_BASEDIR/bin/pip3"
fi

export GATHER_APT_REQUIREMENTS={{shared_dir}}/{{scratch_folder_name}}/apt_reqs.txt
export GATHER_LINKS={{shared_dir}}/{{scratch_folder_name}}/package_links.txt

# Install package python dependencies inside our portable python environment.
if [ -f "$PWD{{requirements_path}}" ]; then
    $PIP_BIN install -U pip setuptools wheel
    $PIP_BIN install {{pip_args}} -r $PWD{{requirements_path}}
fi
$PYTHON_BASEDIR/bin/install_all

$PYTHON_BASEDIR/bin/python3 {{shared_dir}}/{{scratch_folder_name}}/build_tools.py delete_files $PYTHON_BASEDIR/lib/python${PYTHON_VERSION:0:3}/
apt_requirements="{% for dep in runtime_deps %} --depends {{dep}} {% endfor %}"
export excluded="tmsi-dkms"
while read -r p
do
   if [ $excluded != $p ];
   then
     apt_requirements="$apt_requirements --depends $p"
   fi
done < $GATHER_APT_REQUIREMENTS

links=`$PYTHON_BASEDIR/bin/python3 {{shared_dir}}/{{scratch_folder_name}}/build_tools.py`
SITE_PACKAGES="$PYTHON_BASEDIR/lib/python${PYTHON_VERSION:0:3}/site-packages"
while read -r p
do
   links="$links $SITE_PACKAGES/$p"
done < $GATHER_LINKS

# If we have an installer, install our application inside our portable python
# environment.
if [ -f "setup.py" ]; then
    $PYTHON_BIN setup.py install
    setup=true
else
    setup=false
fi

{% if custom_filename %}
    f_name="{{package_tmp_root}}/{{custom_filename}}"
{%else%}
    f_name="{{package_tmp_root}}"
{%endif%}

fpm_args="-s dir -t deb -n {{app}} -p $f_name -v {{version}} $apt_requirements"
echo "$fpm_args"
cd /

# Get rid of VCS info.
find {{package_tmp_root}} -type d -name '.git' -print0 | xargs -0 rm -rf
find {{package_tmp_root}} -type d -name '.svn' -print0 | xargs -0 rm -rf

# If setup==true then we have installed our application inside our portable python
# environment, so we package that environment.
if $setup; then
    fpm  $fpm_args {{fpm_args}} $links $PYTHON_BASEDIR
    cp {{package_tmp_root}}/*deb {{shared_dir}}
# If setup==false then our application is in a different folder than our
# portable python environment. So we package both: our application folder and
# the one with our python package environment. In this case packager should use
# packaging scripts to create proper links and launchers at installation side so
# application is launched using the packaged python environment.
else
    mkdir -p {{package_install_root}}/{{app}}
    cp -r {{package_tmp_root}}/{{app}}/* {{package_install_root}}/{{app}}/
    ls {{package_install_root}}/{{app}}/
    fpm $fpm_args {{fpm_args}} $links $PYTHON_BASEDIR {{package_install_root}}/{{app}}
    cp {{package_tmp_root}}/*deb {{shared_dir}}
fi

chown -R {{local_uid}}:{{local_gid}} {{shared_dir}}
