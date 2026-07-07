package org.example.util;

import java.io.FileWriter;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Base64;

/**
 * Lance ce main UNE SEULE FOIS pour générer les clés RSA
 * Run → GenerateKeys
 */
public class GenerateKeys {

    public static void main(String[] args) throws Exception {

        String dir = "src/main/resources/META-INF/resources/";
        Files.createDirectories(Paths.get(dir));

        // Générer paire de clés RSA 2048 bits
        KeyPairGenerator gen = KeyPairGenerator.getInstance("RSA");
        gen.initialize(2048);
        KeyPair pair = gen.generateKeyPair();

        // Écrire privateKey.pem
        String privateKey = "-----BEGIN PRIVATE KEY-----\n"
                + Base64.getMimeEncoder(64, new byte[]{'\n'})
                .encodeToString(pair.getPrivate().getEncoded())
                + "\n-----END PRIVATE KEY-----\n";
        try (FileWriter fw = new FileWriter(dir + "privateKey.pem")) {
            fw.write(privateKey);
        }

        // Écrire publicKey.pem
        String publicKey = "-----BEGIN PUBLIC KEY-----\n"
                + Base64.getMimeEncoder(64, new byte[]{'\n'})
                .encodeToString(pair.getPublic().getEncoded())
                + "\n-----END PUBLIC KEY-----\n";
        try (FileWriter fw = new FileWriter(dir + "publicKey.pem")) {
            fw.write(publicKey);
        }

        System.out.println("✅ Clés générées dans : " + dir);
        System.out.println("   - privateKey.pem");
        System.out.println("   - publicKey.pem");
    }
}