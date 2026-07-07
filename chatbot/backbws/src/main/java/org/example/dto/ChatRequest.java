package org.example.dto;

import java.util.List;

public class ChatRequest {
    public String       question;
    public String       thread_id       = "";
    public String       user_id         = "";
    public List<String> allowed_modules;
}
