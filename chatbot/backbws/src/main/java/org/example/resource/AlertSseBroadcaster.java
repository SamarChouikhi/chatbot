package org.example.resource;

import io.smallrye.mutiny.Multi;
import io.smallrye.mutiny.subscription.MultiEmitter;
import jakarta.enterprise.context.ApplicationScoped;
import org.example.dto.Alertdto;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Broadcasts newly created alerts to all active SSE subscribers.
 * Each connected client gets its own emitter from newStream().
 */
@ApplicationScoped
public class AlertSseBroadcaster {

    private final CopyOnWriteArrayList<MultiEmitter<String>> emitters = new CopyOnWriteArrayList<>();

    @SuppressWarnings("unchecked")
    public Multi<String> newStream() {
        return Multi.createFrom().emitter(em -> {
            MultiEmitter<String> typed = (MultiEmitter<String>) em;
            emitters.add(typed);
            em.onTermination(() -> emitters.remove(typed));
        });
    }

    public void publish(Alertdto alert) {
        if (emitters.isEmpty()) return;
        String json = serialize(alert);
        List<MultiEmitter<String>> dead = new ArrayList<>();
        for (MultiEmitter<String> em : emitters) {
            if (em.isCancelled()) { dead.add(em); continue; }
            try { em.emit(json); }
            catch (Exception e) { dead.add(em); }
        }
        emitters.removeAll(dead);
    }

    private static String serialize(Alertdto a) {
        return "{\"idDevice\":"  + a.idDevice
             + ",\"type\":\""     + esc(a.type)     + "\""
             + ",\"severity\":\"" + severity(a.type) + "\""
             + ",\"message\":\""  + esc(a.message)   + "\""
             + ",\"value\":"      + (a.valeur != null ? a.valeur : "null")
             + "}";
    }

    private static String severity(String type) {
        if (type == null) return "LOW";
        return switch (type.toUpperCase()) {
            case "LEAK", "FRAUD"                               -> "CRITICAL";
            case "HIGH_CONSO", "OVER_VOLTAGE", "OVER_CURRENT" -> "HIGH";
            default                                            -> "LOW";
        };
    }

    private static String esc(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
    }
}
