package org.example.service;

import com.twilio.Twilio;
import com.twilio.rest.api.v2010.account.Message;
import com.twilio.type.PhoneNumber;
import jakarta.annotation.PostConstruct;
import jakarta.enterprise.context.ApplicationScoped;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.jboss.logging.Logger;

@ApplicationScoped
public class TwilioService {

    private static final Logger LOG = Logger.getLogger(TwilioService.class);

    @ConfigProperty(name = "twilio.account.sid")
    String accountSid;

    @ConfigProperty(name = "twilio.auth.token")
    String authToken;

    @ConfigProperty(name = "twilio.whatsapp.number")
    String whatsappNumber;

    @ConfigProperty(name = "twilio.sms.number", defaultValue = "")
    String smsNumber;

    @PostConstruct
    void init() {
        Twilio.init(accountSid, authToken);
        LOG.info("✅ TwilioService initialisé.");
    }

    /**
     * Envoyer un message WhatsApp via Twilio.
     * Le numéro 'to' doit être au format international : +21612345678
     */
    public void sendWhatsApp(String to, String body) {
        try {
            Message message = Message.creator(
                    new PhoneNumber("whatsapp:" + to),
                    new PhoneNumber(whatsappNumber),
                    body
            ).create();
            LOG.info("WhatsApp envoyé à " + to + " — SID: " + message.getSid());
        } catch (Exception e) {
            LOG.error("Erreur envoi WhatsApp à " + to, e);
            throw new RuntimeException("Échec de l'envoi WhatsApp. Vérifiez le numéro ou la config Twilio.");
        }
    }

    /**
     * Envoyer un SMS classique via Twilio.
     * Utilisé comme fallback si WhatsApp n'est pas disponible.
     */
    public void sendSms(String to, String body) {
        if (smsNumber == null || smsNumber.isBlank()) {
            throw new IllegalStateException("Numéro SMS Twilio non configuré (twilio.sms.number).");
        }
        try {
            Message message = Message.creator(
                    new PhoneNumber(to),
                    new PhoneNumber(smsNumber),
                    body
            ).create();
            LOG.info("SMS envoyé à " + to + " — SID: " + message.getSid());
        } catch (Exception e) {
            LOG.error("Erreur envoi SMS à " + to, e);
            throw new RuntimeException("Échec de l'envoi SMS. Vérifiez le numéro ou la config Twilio.");
        }
    }
}