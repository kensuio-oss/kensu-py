#!/usr/bin/env bash

image_tag=latest

output_dir=$(pwd)
lib_dir=$(pwd)
src_dir=''
options=''

while [[ $# -gt 0 ]]
do
key="$1"

case $key in
    -o)
        output_dir=$(realpath "$2")
        shift # past argument
        ;;
    -lib)
        lib_dir=$(realpath "$2")
        shift # past argument
        ;;
    -encoding|-message-format|-package)
        options="${options} ${1} ${2}"
        shift # past argument
        ;;
    -*)
        options="${options} ${1}"
        ;;
    *)
        src=$(realpath "$1")
        ;;
esac
shift # past argument or value
done

src_dir=$(dirname ${src})
src_file=$(basename ${src})

exec docker run --rm \
     --net=none \
     --user $(id -u):$(id -g) \
     -v ${src_dir}:${src_dir} \
     -v ${output_dir}:${output_dir} \
     -v ${lib_dir}:${lib_dir} \
     petervaczi/antlr:${image_tag} \
     -o ${output_dir} \
     -lib ${lib_dir} \
     ${options} \
     ${src_dir}/${src_file}
