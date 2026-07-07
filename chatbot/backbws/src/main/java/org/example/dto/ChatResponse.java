package org.example.dto;

public class ChatResponse {
    public String answer;
    public String backend;
    public String level;
    public double duration;
    public String thread_id;
    public String message_id;
    public double confidence;

    public ChatResponse() {}

    public ChatResponse(String answer, String backend, String level,
                        double duration, String thread_id,
                        String message_id, double confidence) {
        this.answer     = answer;
        this.backend    = backend;
        this.level      = level;
        this.duration   = duration;
        this.thread_id  = thread_id;
        this.message_id = message_id;
        this.confidence = confidence;
    }
}