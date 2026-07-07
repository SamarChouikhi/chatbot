package org.example.service;

import jakarta.enterprise.context.ApplicationScoped;
import org.example.dto.ChatRequest;
import org.example.dto.ChatResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

@ApplicationScoped
public class AriaService {

    private static final String ARIA_BASE = "http://localhost:8001";

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    private final ObjectMapper mapper = new ObjectMapper();

    public ChatResponse ask(ChatRequest req) throws Exception {
        long start = System.currentTimeMillis();

        String body = mapper.writeValueAsString(req);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(ARIA_BASE + "/chat"))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(190))
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        double duration = (System.currentTimeMillis() - start) / 1000.0;

        if (response.statusCode() != 200) {
            throw new RuntimeException(
                    "ARIA error " + response.statusCode() + " : " + response.body());
        }

        JsonNode json = mapper.readTree(response.body());
        return new ChatResponse(
                json.get("answer").asText(),
                json.path("backend").asText("unknown"),
                json.path("level").asText("2"),
                duration,
                json.path("thread_id").asText(""),
                json.path("message_id").asText(""),
                json.path("confidence").asDouble(0.0)
        );
    }

    public String newThread() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(ARIA_BASE + "/new"))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
        return response.body();
    }

    public String getThreads(String userId) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(ARIA_BASE + "/threads?user_id=" + userId))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
        return response.body();
    }

    public String postFeedback(String body) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(ARIA_BASE + "/feedback"))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
        return response.body();
    }
}