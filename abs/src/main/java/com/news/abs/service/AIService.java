package com.news.abs.service;

import java.net.URI;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

@Service
public class AIService {

    @Value("${ai.service.base-url:http://ai-brain:5005}")
    private String aiBaseUrl;

    private final RestTemplate restTemplate = new RestTemplate();

    public Object callAI(Map<String, Object> request) {
        return restTemplate.postForObject(aiBaseUrl + "/api/v1/personalize", request, Object.class);
    }

    public Object getPersonaScores(String userId) {
        String uid = (userId == null || userId.isBlank()) ? "demo" : userId;
        URI uri = UriComponentsBuilder.fromUriString(aiBaseUrl + "/api/v1/persona-scores")
                .queryParam("user_id", uid)
                .build()
                .toUri();
        return restTemplate.getForObject(uri, Object.class);
    }

    public Object recordHistory(Map<String, Object> body) {
        return restTemplate.postForObject(aiBaseUrl + "/api/v1/history/record", body, Object.class);
    }

    public Object getHistory(String userId, int limit) {
        String uid = (userId == null || userId.isBlank()) ? "demo" : userId;
        URI uri = UriComponentsBuilder.fromUriString(aiBaseUrl + "/api/v1/history")
                .queryParam("user_id", uid)
                .queryParam("limit", limit)
                .build()
                .toUri();
        return restTemplate.getForObject(uri, Object.class);
    }
}
