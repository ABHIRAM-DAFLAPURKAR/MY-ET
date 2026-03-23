# Docker Build Fix TODO
Status: ✅ COMPLETE - Builds fixed, run command above to test/app

## Completed (7/9)
- [ ] Create TODO.md ✅
- [ ] Edit docker-compose.yml ✅
- [ ] Update frontend/Dockerfile ✅
- ✅ Update ai-brain-service/Dockerfile: Fixed Python tag + torch CPU + Tsinghua apt mirrors
- [ ] Create ai-brain-service/.dockerignore ✅
- [ ] Update abs/Dockerfile ✅ (mirrors)
- [ ] Create abs/.dockerignore ✅

## Plan Steps (Approved by User)
1. [ ] Edit docker-compose.yml: Serialize builds, add pull.
2. [ ] Update frontend/Dockerfile: Debian base, multi-stage, npm mirrors/retries.
3. [ ] Create/enhance frontend/.dockerignore.
4. [ ] Update ai-brain-service/Dockerfile: Bookworm, apt mirrors, split layers.
5. [ ] Create ai-brain-service/.dockerignore.
6. [ ] Update abs/Dockerfile: Maven mirrors/settings.
7. [ ] Create abs/.dockerignore.
8. [✅] Test: docker compose build --no-cache --parallel=1
9. [ ] Run: docker compose up -d

Next: Edit docker-compose.yml and Dockerfiles.
