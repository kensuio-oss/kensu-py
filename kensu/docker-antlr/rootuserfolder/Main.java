// package com.company;

import java.io.FileInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;

import org.antlr.v4.gui.SystemFontMetrics;
import org.antlr.v4.runtime.*;
import org.antlr.v4.runtime.tree.*;

public class Main {
    public static void main(String[] args) throws IOException {
        System.out.println("Hello BigQuery Antlr World");
        System.out.println();

        try (Stream<Path> paths = Files.walk(Paths.get("bq_sql_scripts_stan"))) {
            paths
                    .filter(Files::isRegularFile)
                    // .forEach(System.out::println);
                    .forEach(p -> Main.parse(p));
        }
    }

    public static void parse(Path p) {
        try {
            System.out.println();
            System.out.println(p.toString());
            // create a lexer that feeds off of input CharStream
            PostgreSQLLexer lexer = new PostgreSQLLexer(CharStreams.fromPath(p));

            for (Token token = lexer.nextToken();
                 token.getType() != Token.EOF;
                 token = lexer.nextToken()) {
                System.out.print(token);
            }
            lexer.reset();
            System.out.println("SDFSDFSDFSDSDFSFSDF");
            // reset it as it was consumed above
            lexer = new PostgreSQLLexer(CharStreams.fromPath(p));

                // create a buffer of tokens pulled from the lexer
            CommonTokenStream tokens = new CommonTokenStream(lexer);

            // create a parser that feeds off the tokens buffer
            PostgreSQLParser parser = new PostgreSQLParser(tokens);

            // ParseTree tree = parser.query_statement(); // begin parsing at init rule
            ParseTree tree = parser.root(); // begin parsing at init rule
            System.out.println(tree.toStringTree(parser)); // print LISP-style tree
        } catch (IOException e) {
            e.printStackTrace();
        }
    }


    /*
    public static void prettyPrintTokenStream(TokenStream tstream) {
        System.out.println("stream size: " + tstream.size());
        for (int i = 0; i < tstream.size(); i++) {
            Token t = tstream.get(i);

                //if (t.getChannel() != Token.HIDDEN_CHANNEL) {
                //ts.getLine();
                //ts.getCharPositionInLine();
                System.out.print(t.getTokenIndex() + ":" + t.getType() + ":" + t.getText());
                System.out.print(" / ");
            //}
        }
        System.out.println("YALLAH");
    }*/

    /*
    public static void parse(Path p) {
        try {
            System.out.println();
            System.out.println(p.toString());
            // create a lexer that feeds off of input CharStream
            bigqueryLexer lexer = new bigqueryLexer(CharStreams.fromPath(p));

            // create a buffer of tokens pulled from the lexer
            CommonTokenStream tokens = new CommonTokenStream(lexer);

            // create a parser that feeds off the tokens buffer
            bigqueryParser parser = new bigqueryParser(tokens);

            ParseTree tree = parser.query_statement(); // begin parsing at init rule
            System.out.println(tree.toStringTree(parser)); // print LISP-style tree
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
    */

}

