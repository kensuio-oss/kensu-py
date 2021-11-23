#
# setup:
#  docker create --name antlr petervaczi/antlr
#  sudo docker cp antlr:docker-antlr /usr/local/bin/
#  docker rm antlr
#
# use:
#  docker-antlr <antlr-options>
#

# FROM anapsix/alpine-java:8
# MAINTAINER Peter Vaczi <peter.vaczi@gmail.com>

# ENV ANTLR_VERSION 4.6
# ENV CLASSPATH .:/antlr-${ANTLR_VERSION}-complete.jar:$CLASSPATH

# ADD http://www.antlr.org/download/antlr-${ANTLR_VERSION}-complete.jar /
# RUN chmod +r /antlr-${ANTLR_VERSION}-complete.jar

# COPY rootfs/ /

# ENTRYPOINT ["/usr/bin/antlr"]



FROM ubuntu:21.04
MAINTAINER Stanislas Rusinsky <rusinsky@gmail.com>

ENV ANTLR_VERSION 4.9.2
ENV CLASSPATH .:/antlr-${ANTLR_VERSION}-complete.jar:$CLASSPATH

ADD http://www.antlr.org/download/antlr-${ANTLR_VERSION}-complete.jar /
RUN chmod +r /antlr-${ANTLR_VERSION}-complete.jar

COPY rootfs/ /
COPY bashrc/dot_bashrc /root/.bashrc

RUN apt update
RUN apt install -y wget 
RUN wget https://download.java.net/java/GA/jdk17/0d483333a00540d886896bac774ff48b/35/GPL/openjdk-17_linux-x64_bin.tar.gz
RUN tar xvf openjdk-17_linux-x64_bin.tar.gz
RUN mv jdk-17 /opt/
# RUN echo "export JAVA_HOME=/opt/jdk-17" > ~/.bashrc
# RUN echo "export PATH=$PATH:$JAVA_HOME/bin" >> ~/.bashrc

RUN . ~/.bashrc
# RUN java --version


# ENTRYPOINT ["/usr/bin/antlr"]
ENTRYPOINT ["/bin/bash"]
