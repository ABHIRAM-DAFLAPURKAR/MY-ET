package com.news.abs.controller;

import com.news.abs.service.AIService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@RestController
@RequestMapping("/news")
@CrossOrigin(origins = {
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001"
})
public class NewsController {

    @Autowired
    private AIService aiService;

    @GetMapping("/")
    public String health() {
        return "OK";
    }

    @PostMapping("/personalize")
    public Object personalize(@RequestBody Map<String, Object> request) {
        return aiService.callAI(request);
    }

    // NEW: Full Article by ID (mock index -> sample data)
    @GetMapping("/full/{id}")
    public Map<String, Object> getFullArticle(@PathVariable String id) {
        Map<String, Object> mockArticle = new HashMap<>();
        mockArticle.put("id", id);
        mockArticle.put("original_title", "Full Article: " + id);
        mockArticle.put("full_content", "Complete article content loaded from NewsAPI or cache. Personalized adaptation applied based on your reading history and persona preferences. Key highlights: portfolio impact for investors, funding insights for founders, simplified explainers for students.");
        mockArticle.put("transformed_text", "Your personalized version...");
        mockArticle.put("best_persona", "investor");
        mockArticle.put("relevance_score", 0.95);
        Map<String, Double> scores = new HashMap<>();
        scores.put("student", 0.25);
        scores.put("founder", 0.35);
        scores.put("investor", 0.40);
        scores.put("total_confidence", 0.85);
        mockArticle.put("persona_scores", scores);
        return mockArticle;
    }

    // NEW: Similar Articles
    @GetMapping("/similar/{id}")
    public List<Map<String, Object>> getSimilarArticles(@PathVariable String id) {
        List<Map<String, Object>> similars = new ArrayList<>();
        for (int i = 1; i <= 10; i++) {
            Map<String, Object> art = new HashMap<>();
            art.put("title", "Similar Story #" + i + " for " + id);
            art.put("snippet", "AI-matched relevant content based on semantic similarity...");
            art.put("url", "https://mock.news/" + id + "-" + i);
            art.put("relevance", 100 - i * 2.5);
            similars.add(art);
        }
        return similars;
    }

    // NEW: Persona Scores
    @GetMapping("/persona-scores")
    public Object getPersonaScores(@RequestParam(required = false) String user_id) {
        return aiService.getPersonaScores(user_id);
    }

    @PostMapping("/history/record")
    public Object recordHistory(@RequestBody Map<String, Object> body) {
        return aiService.recordHistory(body);
    }

    @GetMapping("/history")
    public Object getHistory(
            @RequestParam String user_id,
            @RequestParam(defaultValue = "50") int limit) {
        return aiService.getHistory(user_id, limit);
    }
}

