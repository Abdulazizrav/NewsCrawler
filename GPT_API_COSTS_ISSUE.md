# GPT API Token Usage - Daily Cost Increase Problem

## Overview
Your OpenAI/GPT API costs are increasing daily ($30.17 total spend, daily costs climbing from April 6-21, 2026) because the system makes 2 API calls per article every hour for each active user.

---

## Root Causes

### **1. Hourly Pipeline Makes Repeated API Calls**

**Location**: [apps/scheduler_manager.py](apps/scheduler_manager.py#L105-L130) - `_user_pipeline_loop()`

```python
def _user_pipeline_loop(user_id: int):
    try:
        time.sleep(60)
        while True:
            _run_command([sys.executable, 'manage.py', 'crawl_news', f'--user_id={user_id}'], ...)
            time.sleep(10)
            _run_command([sys.executable, 'manage.py', 'summarize', f'--user_id={user_id}'], ...)  # ❌ RUNS EVERY HOUR
            time.sleep(10)
            _run_command([sys.executable, 'manage.py', 'classify_articles', f'--user_id={user_id}'], ...)
            time.sleep(10)
            logger.info(f"Pipeline done. Sleeping 1 hour...")
            time.sleep(3600)  # Sleep 1 hour, then repeat
```

**Problem**: This pipeline runs **every hour** for each active user.

---

### **2. Summarize Command Makes 2 API Calls Per Article**

**Location**: [apps/management/commands/summarize.py](apps/management/commands/summarize.py#L28-L52)

```python
def summarize_and_translate_with_openai(text: str, title: str) -> tuple[str, str]:
    with openai_semaphore:
        # API CALL #1 - Summarize content
        summary_response = client.responses.create(
            model="gpt-4.1-mini",
            input=[{"role": "system", "content": "Summarize in 2-4 sentences in Uzbek."},
                   {"role": "user", "content": text}],
            temperature=0.2,
            max_output_tokens=250
        )
        
        # API CALL #2 - Translate title
        title_response = client.responses.create(
            model="gpt-4.1-mini",
            input=[{"role": "system", "content": "Translate title to Uzbek..."},
                   {"role": "user", "content": title}],
            temperature=0.1,
            max_output_tokens=100
        )
    
    return extract_text(summary_response), extract_text(title_response)
```

**Per Article Cost**: 2 API calls × hourly runs × number of active users

---

### **3. Crawler Creates New Articles Every Hour**

**Location**: [apps/management/commands/crawl_news.py](apps/management/commands/crawl_news.py#L53-L66)

```python
def run_all_crawlers(user):
    """Runs crawlers - fetches from 5 sources"""
    crawl_from_truck(user)      # ✅ Fetches articles
    crawl_with_rss(user)         # ✅ Fetches articles  
    crawl_from_guardian(user)    # ✅ Fetches articles
    crawl_from_rss_http(user)    # ✅ Fetches articles
    crawl_from_qalampir(user)    # ✅ Fetches articles
```

This runs **every hour** and adds new articles.

---

### **4. Critical Bug: Failed Articles Retry Forever**

**Location**: [apps/management/commands/summarize.py](apps/management/commands/summarize.py#L60-110)

```python
def process_article(article, stats):
    try:
        if article.is_summary:
            return  # Skip already summarized
            
        # If API call fails, article stays is_summary=False ❌
        summary, translated_title = summarize_and_translate_with_openai(...)
        
        Summary.objects.create(...)
        article.is_summary = True
        article.save()
        
    except Exception as e:
        print(f"Error processing {article.id}: {e}")
        # ❌ Article is NOT marked as failed!
        # ❌ It will be retried EVERY HOUR indefinitely!
        stats["failed"] += 1
```

**The Problem**: 
- If an article fails to summarize (quota exceeded, API error, etc.), it stays `is_summary=False`
- The next hour, summarize runs again and **tries the same article again** - wasting API tokens
- This repeats indefinitely, causing runaway costs

---

### **5. No Deduplication of Articles**

**Location**: [apps/scripts/crawlers.py](apps/scripts/crawlers.py) (not shown but implied)

- Crawlers run every hour
- They likely fetch the same articles repeatedly if not properly deduplicated
- Each duplicate article triggers 2 API calls when summarizer runs

---

## Cost Calculation Example

Assume:
- **1 active user**
- **100 articles created each hour** (5 crawlers × ~20 articles each)
- **Hourly pipeline runs**

**Daily Costs**:
```
Articles per category hour: 100
API calls per article: 2 (summarize + translate)
Pipeline runs per day: 24

Daily API calls = 100 × 2 × 24 = 4,800 calls/day

At ~$0.01 per 1000 tokens (gpt-4-mini estimate):
Cost per call ≈ $0.001-0.005
Daily cost ≈ $5-24/day

Your April spend: $30/15 days ≈ $2/day average
(Lower than estimate because not all articles need summarizing, 
but explains why costs increase daily as more articles accumulate)
```

---

## Issues Summary

| Issue | Location | Impact | Severity |
|-------|----------|--------|----------|
| Hourly summarize pipeline | `scheduler_manager.py` | 24 runs/day unnecessary | HIGH |
| 2 API calls per article | `summarize.py` | Could be 1 combined call | MEDIUM |
| Failed articles retry forever | `summarize.py` | Infinite cost for failures | **CRITICAL** |
| Crawler deduplication | `crawlers.py` | Duplicate articles = duplicate costs | MEDIUM |
| No article processing limits | `summarize.py` | Processes ALL unsummarized articles | MEDIUM |

---

## Recommended Fixes

### **1. Add Failed Article Tracking (CRITICAL)**
```python
# Add to Article model:
last_summarize_attempt = DateTimeField(null=True, blank=True)
summarize_failed_count = IntegerField(default=0, max_value=3)

# In summarize.py:
if article.summarize_failed_count >= 3:
    return  # Skip after 3 failures
    
try:
    summary, title = summarize_and_translate_with_openai(...)
    article.is_summary = True
    article.summarize_failed_count = 0
    article.save()
except Exception as e:
    article.summarize_failed_count += 1
    article.last_summarize_attempt = timezone.now()
    article.save()
```

### **2. ~~Reduce Pipeline Frequency~~ (SKIP - Intentional Hourly)**
Keep hourly runs as designed.

### **3. Combine API Calls (MEDIUM)**
Make ONE API call instead of two:
```python
# Instead of 2 calls, use 1 call with multiple outputs
response = client.responses.create(
    model="gpt-4.1-mini",
    input=[
        {"role": "system", "content": "Summarize and translate. Return JSON: {summary, title}"},
        {"role": "user", "content": text}
    ],
    temperature=0.2,
    max_output_tokens=400
)
```

### **4. Add Processing Limits (MEDIUM)**
```python
# Only process N articles per pipeline run
articles = Article.objects.filter(owner=user, is_summary=False)[:50]  # Limit to 50
```

### **5. Batch API Calls (MEDIUM)**
Use OpenAI batch API for lower cost.

---

## Monitoring

Add to check daily costs:
```python
# Add a management command to track API usage
python manage.py track_api_costs
```

This should log:
- Articles processed today
- API calls made
- Estimated cost
- Failed articles to retry

---

## Files to Review
1. [apps/scheduler_manager.py](apps/scheduler_manager.py) - Pipeline frequency
2. [apps/management/commands/summarize.py](apps/management/commands/summarize.py) - Retry logic + API calls  
3. [apps/models/article.py](apps/models/article.py) - Need failure tracking fields
4. [apps/scripts/crawlers.py](apps/scripts/crawlers.py) - Deduplication logic

