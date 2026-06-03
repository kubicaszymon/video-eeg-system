ARG UBUNTU_VERSION=18.04
FROM ubuntu:$UBUNTU_VERSION
RUN apt-get update && apt-get install -y \
    curl git ruby ruby-dev rubygems build-essential \
    make build-essential libssl-dev zlib1g-dev libbz2-dev libsqlite3-dev portaudio19-dev \
    && rm -rf /var/lib/apt/lists/* && apt-get clean
RUN gem install --no-ri --no-rdoc fpm
ENV PYTHON_VERSION 3.6.6
ENV PYTHON_BASEDIR /opt/braintech-svarog-streamer-python
RUN cd /var/tmp \
    && curl -O https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz \
    && tar xzvf Python-$PYTHON_VERSION.tgz \
    && cd Python-$PYTHON_VERSION \
    && ./configure --prefix=$PYTHON_BASEDIR --with-ensurepip=install \
    && make && make install
