# 1) build the Docker image

```
# go in the docker-antlr folder 
# build the image from the dockerfile
docker build -t antlr:latest .
# run it 
# because there's an entrypoint in the Dockerfile th option --entrypoint is necessary
docker run --name lucky_shmulik --mount type=bind,source=/Users/stan/src/docker-antlr/rootuserfolder,target=/root -it --entrypoint /bin/bash antlr
# if it was run before, next time you can jsut start it and launch a shell in it
docker start lucky_shmulik
docker exec -it lucky_shmulik /bin/bash

# to delete it if you modified the Dockerfile for example and want to rebuid it: 
docker stop lucky_shmulik
docker rm lucky_shmulik
````


# 2) compile the Antlr bigquery grammar 

the `.bashrc` file has the following entries:

```
export ANTLR_VERSION="4.9.2"  
export ANTLR_JAR="/antlr-${ANTLR_VERSION}-complete.jar"  
export JAVA_HOME=/opt/jdk-17  
export PATH=$PATH:$JAVA_HOME/bin  
# a for antlr  
alias a="java -jar ${ANTLR_JAR}"  
# c for compile  
alias c="javac -cp /root/:${ANTLR_JAR} *.java"# r for run  
alias r="java -cp /root/:${ANTLR_JAR} Main"  
alias g="java -cp /root/:${ANTLR_JAR} org.antlr.v4.gui.TestRig"
```

so in the docker image you can just simply 
`cd /root/; a bigquery.g4 ; c ; r` to buil everything and run the tests
The Main java program reads the sql files from the *bq_sql_scripts* and parses them


# 3) execute the SQL interpreter 

#TODO method (python or java?) to run on a single file or string so it can be called from the collector wrapper 

#TODO to develop both from Docker and from the local IDE, improve the Dockerfile so as to mount the folder and make it possible to access the grammar and sql files from host and container


