# 🎓 INTERN INTERVIEW GUIDE - Real Estate CLIP API

## 🎯 Dành cho: Intern/Junior Position (0-1 year experience)

> **Scenario:** Demo qua meeting (screen share) với nhà tuyển dụng
> **Duration:** 30-45 phút
> **Focus:** Hiểu project, basic concepts, learning mindset

---

## 📋 DEMO SCRIPT (15 phút)

### **Part 1: Project Overview (3 phút)**

**Script:**
> "Chào anh/chị, em xin giới thiệu project Real Estate Search API. Đây là một API tìm kiếm bất động sản với tính năng phân tích hình ảnh bằng AI."

**Show:** README.md hoặc architecture diagram

**Key points:**
- ✅ "Project này giúp tìm kiếm thông tin nhà đất từ nhiều website"
- ✅ "Sử dụng AI (CLIP model) để hiểu hình ảnh"
- ✅ "Deploy lên Google Cloud với Kubernetes"

---

### **Part 2: Live Demo (5 phút)**

#### **Step 1: Show API endpoint**
```bash
# Terminal 1: Show service running
kubectl get pods -n property-ns
# Output: 3 pods running

kubectl get svc -n property-ns property-service
# Output: EXTERNAL-IP: 34.x.x.x
```

**Explain:**
> "Em deploy 3 pods để đảm bảo service luôn available. Nếu 1 pod die thì còn 2 pods khác."

---

#### **Step 2: Make API request**
```bash
# Terminal 2: Call API
curl -X POST http://34.x.x.x/search \
  -H "Content-Type: application/json" \
  -d '{
    "address": "107/131 Adelaide Terrace, East Perth WA 6004",
    "include_embeddings": false
  }'
```

**Explain:**
> "API này nhận địa chỉ, tìm kiếm trên domain.com.au và realestate.com.au, trả về thông tin như giá, số phòng ngủ, hình ảnh."

**Show response:**
```json
{
  "properties": [
    {
      "source": "domain",
      "address": "107/131 Adelaide Terrace, East Perth WA 6004",
      "price": "$1,150,000",
      "bedrooms": 2,
      "bathrooms": 2,
      "image_urls": ["https://..."]
    }
  ]
}
```

---

#### **Step 3: Show with embeddings (optional)**
```bash
curl -X POST http://34.x.x.x/search \
  -H "Content-Type: application/json" \
  -d '{
    "address": "107/131 Adelaide Terrace, East Perth WA 6004",
    "include_embeddings": true,
    "max_images": 3
  }'
```

**Explain:**
> "Khi bật embeddings, API sẽ dùng CLIP model để phân tích hình ảnh, tạo ra vector 512 chiều. Vector này có thể dùng để tìm các property tương tự về mặt hình ảnh."

---

#### **Step 4: Show caching**
```bash
# Call API lần 2 (same address)
time curl -X POST http://34.x.x.x/search ...

# First call: 5-10 seconds
# Second call: 0.1 seconds (from cache!)
```

**Explain:**
> "Em implement Redis cache để tăng tốc. Lần đầu gọi sẽ scrape từ website (chậm), lần sau lấy từ cache (nhanh)."

---

### **Part 3: Show Code (5 phút)**

#### **Open VSCode, show main.py**

**Line 103-107: API endpoint**
```python
@app.post("/search", response_model=SearchResponse)
async def search_property(address: str, body: SearchRequest):
    addr = address or body.address
    include_embeddings = body.include_embeddings
```

**Explain:**
> "Đây là endpoint chính. Em dùng FastAPI vì nó support async/await, giúp xử lý nhiều request cùng lúc."

---

**Line 121-123: Cache check**
```python
cached = get_from_cache(addr)
if cached is not None and include_embeddings:
    return {"properties": [Property(**_normalize_payload(p)) for p in cached]}
```

**Explain:**
> "Trước khi scrape, em check cache trước. Nếu có rồi thì return luôn, không cần scrape lại."

---

**Line 91-97: Concurrent scraping**
```python
tasks = []
if domain_url:
    tasks.append(_scrape_domain(domain_url))
if realestate_url:
    tasks.append(_scrape_realestate(realestate_url))
props = await asyncio.gather(*tasks)  # Parallel!
```

**Explain:**
> "Em scrape 2 website đồng thời (parallel) thay vì tuần tự. Điều này giúp giảm thời gian từ 10s xuống 5s."

---

#### **Show kubernetes/resources.yaml**

**Line 31-50: Deployment**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: property-api
spec:
  replicas: 3  # 3 pods for high availability
```

**Explain:**
> "Em deploy 3 replicas để đảm bảo high availability. Nếu 1 pod crash, Kubernetes tự động restart và traffic vẫn đi qua 2 pods còn lại."

---

**Line 130-143: Auto-scaling**
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

**Explain:**
> "Em config auto-scaling. Khi CPU > 70%, Kubernetes tự động tăng số pods từ 2 lên 10 để handle traffic."

---

### **Part 4: Monitoring (2 phút)**

```bash
# Show logs
kubectl logs -n property-ns -l app=property-api --tail=20

# Show resource usage
kubectl top pods -n property-ns
```

**Explain:**
> "Em có thể xem logs để debug và monitor resource usage (CPU, memory) của từng pod."

---

## 🎤 30 CÂU HỎI INTERN LEVEL (Dễ → Khó)

### **CATEGORY 1: Basic Understanding (Q1-10) ⭐ MUST KNOW**

#### **Q1. Project này làm gì?**
**Answer:**
> "Project này là một API tìm kiếm thông tin bất động sản. Người dùng gửi địa chỉ, API sẽ tự động tìm kiếm trên domain.com.au và realestate.com.au, lấy thông tin như giá, số phòng, hình ảnh. Ngoài ra còn có tính năng phân tích hình ảnh bằng AI (CLIP model) để tìm các property tương tự."

**Demo:** Show API request/response

---

#### **Q2. Tại sao dùng FastAPI?**
**Answer:**
> "Em chọn FastAPI vì:
> 1. **Async/await** - Xử lý nhiều request cùng lúc (concurrent)
> 2. **Tự động validation** - Pydantic check input/output
> 3. **Auto docs** - Có sẵn /docs endpoint để test API
> 4. **Nhanh** - Nhanh hơn Flask 2-3 lần cho I/O-bound tasks"

**Demo:** Open http://API/docs (Swagger UI)

---

#### **Q3. Redis dùng để làm gì?**
**Answer:**
> "Redis là cache để lưu kết quả đã scrape. Lần đầu gọi API sẽ scrape từ website (5-10s), lần sau lấy từ cache (0.1s). Cache có TTL 48 giờ, sau đó tự động xóa."

**Demo:** 
```bash
# Show cache hit vs miss
time curl ... # First: 5s
time curl ... # Second: 0.1s
```

---

#### **Q4. CLIP model là gì?**
**Answer:**
> "CLIP là AI model của OpenAI, hiểu cả hình ảnh và text. Em dùng nó để chuyển hình ảnh property thành vector 512 số (embedding). Các property có hình ảnh giống nhau sẽ có vector gần nhau, giúp tìm property tương tự."

**Visual:**
```
Image → CLIP → [0.123, -0.456, ..., 0.789] (512 numbers)
                      ↓
              Compare vectors
                      ↓
          Find similar properties
```

---

#### **Q5. Kubernetes là gì? Tại sao dùng?**
**Answer:**
> "Kubernetes (K8s) là platform quản lý containers. Em dùng K8s vì:
> 1. **Auto-scaling** - Tự động tăng/giảm pods theo traffic
> 2. **Self-healing** - Pod crash thì tự restart
> 3. **Load balancing** - Phân traffic đều cho 3 pods
> 4. **Zero-downtime deployment** - Update code không downtime"

**Demo:** `kubectl get pods` (show 3 replicas)

---

#### **Q6. Giải thích flow từ request đến response?**
**Answer:**
```
1. Client gửi POST /search với address
2. API check Redis cache
3. Nếu cache miss → Tìm URL trên domain.com.au, realestate.com.au
4. Scrape 2 websites đồng thời (parallel)
5. Nếu include_embeddings=true → Dùng CLIP extract embeddings
6. Lưu vào Redis cache (TTL 48h)
7. Return JSON response
```

**Demo:** Show code từng bước trong main.py

---

#### **Q7. Làm sao scrape được data từ website?**
**Answer:**
> "Em dùng thư viện `requests` để download HTML, sau đó dùng `BeautifulSoup` để parse và extract thông tin. Ví dụ:
> ```python
> html = requests.get(url).text
> soup = BeautifulSoup(html, 'html.parser')
> price = soup.select_one('.price').text
> ```
> Em cũng có nhiều parsing strategies để handle khi website thay đổi HTML structure."

---

#### **Q8. Async/await hoạt động thế nào?**
**Answer:**
> "Async/await giúp code chạy concurrent (đồng thời) mà không cần threads. Khi gặp I/O operation (network, file), Python không đợi mà chuyển sang task khác.
> 
> Ví dụ: Scrape 2 websites
> ```python
> # Sync: 5s + 5s = 10s
> data1 = scrape_domain(url1)  # Wait 5s
> data2 = scrape_realestate(url2)  # Wait 5s
> 
> # Async: max(5s, 5s) = 5s
> tasks = [scrape_domain(url1), scrape_realestate(url2)]
> data = await asyncio.gather(*tasks)  # Both run together!
> ```

---

#### **Q9. Docker là gì? Tại sao cần?**
**Answer:**
> "Docker đóng gói app + dependencies vào container. Container chạy giống nhau trên mọi môi trường (laptop, server, cloud).
> 
> **Benefits:**
> - ✅ Consistent environment (không có 'works on my machine')
> - ✅ Easy deployment (chỉ cần pull image)
> - ✅ Isolation (mỗi app trong container riêng)"

**Demo:** Show Dockerfile

---

#### **Q10. Deployment process như thế nào?**
**Answer:**
```bash
# 1. Build Docker image
docker build -t property-api:v1.0 .

# 2. Push to Google Artifact Registry
docker push australia-southeast1-docker.pkg.dev/.../property-api:v1.0

# 3. Deploy to Kubernetes
kubectl apply -f kubernetes/resources.yaml

# 4. Verify
kubectl get pods -n property-ns
kubectl get svc property-service
```

---

### **CATEGORY 2: Technical Details (Q11-20) ⚠️ MEDIUM**

#### **Q11. Tại sao có 3 replicas?**
**Answer:**
> "3 replicas để đảm bảo high availability:
> - 1 pod crash → Còn 2 pods handle traffic
> - Rolling update → Luôn có 2 pods available (PodDisruptionBudget)
> - Load balancing → Traffic phân đều cho 3 pods
> 
> Trade-off: Chi phí tăng 3x ($204/month vs $68 cho 1 pod)"

---

#### **Q12. Cache TTL 48h có hợp lý không?**
**Answer:**
> "48h hơi dài vì thông tin property thay đổi hàng ngày (giá, sold status). Em nghĩ 12-24h sẽ tốt hơn để data fresh hơn.
> 
> **Trade-off:**
> - TTL cao → Ít scraping, nhanh, nhưng data có thể stale
> - TTL thấp → Data fresh, nhưng scraping nhiều hơn, chậm hơn"

---

#### **Q13. Nếu Redis crash thì sao?**
**Answer:**
> "Hiện tại Redis chỉ có 1 replica (single point of failure). Nếu crash:
> - ✅ API vẫn hoạt động (scrape trực tiếp)
> - ❌ Mọi request đều chậm (5-10s thay vì 0.1s)
> - ❌ Cache data mất hết
> 
> **Solution:** Deploy Redis Sentinel (3 replicas) với auto-failover."

---

#### **Q14. Làm sao handle khi website block scraping?**
**Answer:**
> "Em có nhiều strategies:
> 1. **User-Agent** - Giả làm browser
> 2. **Rate limiting** - CRAWL_DELAY=5s giữa requests
> 3. **Retry logic** - Exponential backoff khi bị rate limit
> 4. **Multiple search strategies** - Domain search → Bing → DuckDuckGo
> 5. **ScrapingBee fallback** - Paid service với rotating IPs"

---

#### **Q15. CLIP model nặng bao nhiêu? Load lâu không?**
**Answer:**
> "CLIP ViT-B/32:
> - Model size: ~350MB (download)
> - Memory usage: ~1.5GB (loaded)
> - Startup time: 60-90s lần đầu, 30s lần sau (cached)
> 
> Em load model 1 lần khi pod start (`@app.on_event('startup')`), không load lại mỗi request."

---

#### **Q16. CPU vs GPU cho CLIP?**
**Answer:**
> "Hiện tại em dùng CPU:
> - CPU: ~2s per image
> - GPU (T4): ~0.02s per image (100x faster!)
> 
> **Why CPU:** Cost-effective ($68/pod vs $200 với GPU)
> **When GPU:** Khi scale lên > 1000 users, cần response time < 5s"

---

#### **Q17. Pydantic validation hoạt động thế nào?**
**Answer:**
```python
# schemas.py
class SearchRequest(BaseModel):
    address: str  # Required
    include_embeddings: bool = True  # Default
    max_images: int = 12

# FastAPI tự động validate
@app.post("/search")
async def search_property(body: SearchRequest):
    # Nếu client gửi sai type → Auto return 422 error
    # Nếu missing address → Auto return 422
```

**Demo:** Send invalid request, show error

---

#### **Q18. Làm sao compress cache data?**
**Answer:**
```python
# app/cache.py line 30-33
payload = zlib.compress(json.dumps(data).encode("utf-8"))
redis_client.setex(key, ttl, payload)

# Typical compression: 12KB → 3KB (75% reduction)
```

> "Em dùng zlib compress JSON trước khi lưu Redis. Giúp tiết kiệm memory và network bandwidth."

---

#### **Q19. HorizontalPodAutoscaler hoạt động thế nào?**
**Answer:**
```yaml
minReplicas: 2
maxReplicas: 10
targetCPUUtilizationPercentage: 70

# Behavior:
# CPU < 70% → Scale down (1 pod every 5 min)
# CPU > 70% → Scale up (double pods every 3 min)
```

> "K8s monitor CPU usage mỗi 15s. Khi CPU > 70% trong 3 phút, tự động tăng pods. Khi CPU < 70% trong 5 phút, giảm pods."

---

#### **Q20. Concurrent scraping nhanh hơn bao nhiêu?**
**Answer:**
```python
# Sequential (sync):
data1 = scrape_domain(url1)      # 5s
data2 = scrape_realestate(url2)  # 5s
# Total: 10s

# Concurrent (async):
tasks = [scrape_domain(url1), scrape_realestate(url2)]
data = await asyncio.gather(*tasks)
# Total: 5s (both run in parallel)

# Speedup: 2x faster!
```

---

### **CATEGORY 3: Problem Solving (Q21-30) 🔥 HARDER**

#### **Q21. API trả về 500 error, debug thế nào?**
**Answer:**
```bash
# Step 1: Check logs
kubectl logs -n property-ns -l app=property-api --tail=50

# Step 2: Common causes
# - Redis connection failed
# - CLIP model not loaded
# - Scraping timeout
# - OOM (out of memory)

# Step 3: Check pod status
kubectl describe pod property-api-xxx

# Step 4: Test components
kubectl exec -it property-api-xxx -- python -c "import redis; redis.Redis(host='redis-service').ping()"
```

---

#### **Q22. Response time chậm (30s), làm sao tối ưu?**
**Answer:**
> "Bottleneck là CLIP embeddings (15-30s). Solutions:
> 1. **GPU** - 100x faster (0.3s thay vì 30s)
> 2. **Reduce max_images** - 12 → 6 images (2x faster)
> 3. **Async workers** - Separate CLIP processing, return job ID immediately
> 4. **Pre-compute** - Cache embeddings cho popular properties
> 5. **Batch processing** - Process 12 images cùng lúc thay vì tuần tự"

---

#### **Q23. Nếu traffic tăng 10x thì sao?**
**Answer:**
> "Current: 6 RPS → Need: 60 RPS
> 
> **Solutions:**
> 1. **HPA scale up** - 3 → 10 pods (handle 20 RPS)
> 2. **Separate CLIP workers** - API pods không chạy CLIP
> 3. **Message queue** - Pub/Sub để buffer requests
> 4. **GPU nodes** - T4 GPU cho CLIP (100x faster)
> 5. **Redis Cluster** - 6 nodes thay vì 1
> 
> **Cost:** $225/month → $1,500/month"

---

#### **Q24. Làm sao test API locally trước khi deploy?**
**Answer:**
```bash
# 1. Run Redis locally
docker run -d -p 6379:6379 redis:7-alpine

# 2. Set environment variables
export REDIS_HOST=localhost
export REDIS_PORT=6379

# 3. Run API
python -m uvicorn app.main:app --reload

# 4. Test
curl -X POST http://localhost:8000/search -d '{"address": "..."}'

# 5. Check logs
# See output in terminal
```

---

#### **Q25. Security: API có cần authentication không?**
**Answer:**
> "Có! Hiện tại API không có auth (anyone có thể gọi). Production cần:
> 1. **API Key authentication** - Client gửi key trong header
> 2. **JWT tokens** - User login, nhận token
> 3. **Rate limiting** - Giới hạn requests per user
> 4. **HTTPS** - Encrypt traffic
> 
> Em biết đây là gap và có thể implement nếu cần."

---

#### **Q26. Làm sao monitor API trong production?**
**Answer:**
> "Em sẽ setup:
> 1. **Prometheus** - Collect metrics (latency, error rate, throughput)
> 2. **Grafana** - Dashboard visualization
> 3. **Alerting** - Alert khi error rate > 5% hoặc latency > 10s
> 4. **Logging** - Centralized logs với ELK stack
> 5. **Tracing** - Distributed tracing với Jaeger
> 
> Hiện tại em chỉ có kubectl logs (basic)."

---

#### **Q27. Nếu 1 pod crash, traffic có bị ảnh hưởng không?**
**Answer:**
> "Không! Vì:
> 1. **3 replicas** - Còn 2 pods handle traffic
> 2. **readinessProbe** - K8s không route traffic đến unhealthy pod
> 3. **Auto-restart** - K8s tự động restart crashed pod
> 4. **PodDisruptionBudget** - Đảm bảo min 2 pods available
> 
> Downtime: 0 seconds (seamless failover)"

---

#### **Q28. Cost optimization: Giảm chi phí thế nào?**
**Answer:**
> "Current: $225/month
> 
> **Optimizations:**
> 1. **Preemptible nodes** - 80% cheaper ($45/month)
> 2. **Reduce resources** - CPU 500m→250m, Memory 3Gi→2Gi
> 3. **Autopilot mode** - GKE quản lý, chỉ trả tiền pods
> 4. **Reduce replicas** - 3 → 2 (still HA)
> 5. **Smaller Redis** - 5Gi → 1Gi PVC
> 
> **Result:** $225 → $80/month (64% savings)"

---

#### **Q29. Multi-region deployment có cần không?**
**Answer:**
> "Depends on requirements:
> 
> **Current (single region):**
> - ✅ Simple, cheap ($225/month)
> - ❌ Regional outage = total downtime
> - ❌ High latency for global users
> 
> **Multi-region:**
> - ✅ Global coverage (< 100ms latency worldwide)
> - ✅ Regional failover (99.95% uptime)
> - ❌ Complex setup
> - ❌ 3x cost ($675/month)
> 
> **For intern project:** Single region OK. **For production:** Multi-region recommended."

---

#### **Q30. Học được gì từ project này?**
**Answer:**
> "Em học được:
> 1. **Kubernetes** - Deployment, Service, HPA, PDB, RollingUpdate
> 2. **Async Python** - FastAPI, asyncio, concurrent programming
> 3. **ML Integration** - CLIP model, embeddings, vector similarity
> 4. **Web Scraping** - BeautifulSoup, multi-strategy search, resilience
> 5. **Cloud Deployment** - GKE, Docker, Artifact Registry
> 6. **System Design** - Caching, load balancing, high availability
> 7. **Debugging** - kubectl logs, describe, troubleshooting
> 
> **Challenges:**
> - Rate limiting từ websites
> - CLIP performance trên CPU
> - Kubernetes learning curve
> 
> **Next steps:**
> - Add authentication
> - Implement monitoring (Prometheus)
> - GPU deployment
> - CI/CD pipeline"

---

## 🎯 DEMO TIPS

### **Before Demo:**
- [ ] Test API works (curl command ready)
- [ ] Pods running (kubectl get pods)
- [ ] Have code open in VSCode
- [ ] Architecture diagram ready
- [ ] Practice explaining flow

### **During Demo:**
- ✅ **Speak slowly and clearly**
- ✅ **Show, don't just tell** (run commands, show code)
- ✅ **Explain WHY, not just WHAT** (why FastAPI, why 3 replicas)
- ✅ **Acknowledge limitations** (no auth, single Redis, CPU-bound)
- ✅ **Show learning mindset** ("Em biết X là gap, em có thể học Y")

### **Common Mistakes to Avoid:**
- ❌ Too much jargon (explain simply)
- ❌ Rushing through demo
- ❌ Not testing beforehand
- ❌ Saying "I don't know" (say "I haven't learned that yet, but I can research")
- ❌ Overconfident (be humble, show willingness to learn)

---

## 📊 Scoring Guide (Intern Level)

### **Excellent (90-100%)**
- Understand all 30 questions
- Can explain architecture clearly
- Demo works smoothly
- Show learning mindset
- Ask good questions

### **Good (70-90%)**
- Understand Q1-20 well
- Can demo basic features
- Some gaps in advanced topics (OK for intern!)
- Willing to learn

### **Acceptable (50-70%)**
- Understand Q1-10 (basics)
- Demo works (even if not perfect)
- Honest about what you don't know
- Enthusiastic to learn

### **Need Improvement (< 50%)**
- Can't explain basic concepts
- Demo doesn't work
- No understanding of code
- Not prepared

---

## 💡 Sample Answers for Tough Questions

### **"Why should we hire you?"**
> "Em có passion về technology và đã tự học để build project này từ đầu. Em có thể deploy production Kubernetes, integrate ML models, và debug issues. Em biết mình còn nhiều điều phải học, nhưng em có growth mindset và sẵn sàng học hỏi từ senior engineers. Project này chứng minh em có thể tự học và deliver working product."

### **"What's your biggest weakness?"**
> "Em chưa có kinh nghiệm làm việc team và production environment. Em biết code của em chưa perfect (thiếu auth, monitoring, tests). Nhưng em eager to learn best practices từ team và improve code quality. Em cũng đang học thêm về security và testing."

### **"Where do you see yourself in 2 years?"**
> "Em muốn trở thành mid-level engineer với expertise về cloud-native applications và ML systems. Em muốn contribute to production systems, learn from senior engineers, và eventually mentor junior developers. Project này là starting point, em sẽ continue building và learning."

---

## ✅ Final Checklist

**1 day before:**
- [ ] Test demo end-to-end
- [ ] Review Q1-20 (must know)
- [ ] Practice explaining architecture (< 5 min)
- [ ] Prepare 3 questions for interviewer

**1 hour before:**
- [ ] Check pods running
- [ ] Test API endpoint
- [ ] Have VSCode open with code
- [ ] Calm down, breathe

**During interview:**
- [ ] Confident but humble
- [ ] Show enthusiasm
- [ ] Ask for clarification if needed
- [ ] Thank interviewer at end

---

## 🚀 You got this! Good luck with your intern interview! 💪

**Remember:** Intern position focuses on **potential and learning ability**, not perfect knowledge. Show that you can learn, build, and grow!
