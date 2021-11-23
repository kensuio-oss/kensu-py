export ANTLR_VERSION="4.9.2"
export ANTLR_JAR="/antlr-${ANTLR_VERSION}-complete.jar"
export JAVA_HOME=/opt/jdk-17
export PATH=$PATH:$JAVA_HOME/bin
# a for antlr
alias a="java -jar ${ANTLR_JAR}"
# c for compile
alias c="javac -cp /root/:${ANTLR_JAR} *.java"
# r for run
alias r="java -cp /root/:${ANTLR_JAR} Main"

alias g="java -cp /root/:${ANTLR_JAR} org.antlr.v4.gui.TestRig"


alias ll='ls -l'
alias l='ls -lA'