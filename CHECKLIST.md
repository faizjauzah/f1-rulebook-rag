# F1 Rulebook RAG - Setup Checklist

## Pre-Deployment Checklist

### Local Development

- [ ] **Prerequisites installed**
  - [ ] Docker Desktop installed and running
  - [ ] Docker Compose available (`docker-compose --version`)
  - [ ] Python 3.11+ (for local eval script testing)
  - [ ] curl (for API testing)

- [ ] **API Keys configured**
  - [ ] Created `.env` file from `.env.example`
  - [ ] Added valid `GOOGLE_API_KEY` from https://ai.google.dev/
  - [ ] Verified API key works (test at https://aistudio.google.com/)

- [ ] **PDFs present**
  - [ ] All 6 F1 regulation PDFs in `PDFs/` directory
  - [ ] Filenames match expected pattern (Section X [Name])

- [ ] **Configuration reviewed**
  - [ ] Checked `config.yaml` profile setting (cloud/local)
  - [ ] Adjusted `top_k`, `similarity_threshold` if needed
  - [ ] For local mode: LM Studio installed and model loaded

### First Run

- [ ] **Start services**
  ```bash
  ./run.sh start
  # or: docker-compose up --build
  ```

- [ ] **Wait for healthy status**
  - [ ] API logs show "Application startup complete"
  - [ ] ChromaDB healthcheck passes
  - [ ] `./run.sh health` returns status "healthy"

- [ ] **Run ingestion**
  ```bash
  ./run.sh ingest
  # Wait 5-20 minutes depending on profile
  ```
  - [ ] No errors in logs
  - [ ] Response shows "chunks_created" > 300

- [ ] **Smoke test**
  ```bash
  ./smoke_test.sh
  ```
  - [ ] All 5 tests pass

- [ ] **Try web UI**
  - [ ] Open http://localhost:8000
  - [ ] Ask a test question
  - [ ] Verify answer and sources display correctly

### Validation

- [ ] **Run evaluation**
  ```bash
  ./run.sh eval
  ```
  - [ ] 10/10 questions successful
  - [ ] Average response time < 10 seconds
  - [ ] Review `eval/results.json`

- [ ] **Manual testing**
  - [ ] Test easy question (e.g., "What is DRS?")
  - [ ] Test medium question (cross-article)
  - [ ] Test hard question (interpretation)
  - [ ] Test off-topic question (should decline gracefully)
  - [ ] Test both profiles (cloud and local if available)

## Cloud Deployment Checklist (Fly.io)

- [ ] **Fly.io setup**
  - [ ] Install flyctl: https://fly.io/docs/flyctl/install/
  - [ ] Login: `fly auth login`
  - [ ] Create account if needed

- [ ] **Launch app**
  ```bash
  fly launch
  ```
  - [ ] Choose app name
  - [ ] Select region (closest to you)
  - [ ] Don't deploy yet (set secrets first)

- [ ] **Configure secrets**
  ```bash
  fly secrets set GOOGLE_API_KEY=your_actual_key
  ```

- [ ] **Create persistent volume**
  ```bash
  fly volumes create chroma_data --size 1
  ```

- [ ] **Update fly.toml** (if needed)
  - [ ] Add volume mount
  - [ ] Adjust memory/CPU if needed
  - [ ] Set health check endpoint

- [ ] **Deploy**
  ```bash
  fly deploy
  ```

- [ ] **Run ingestion** (one-time)
  ```bash
  curl -X POST https://your-app.fly.dev/ingest
  # Wait 5-20 minutes
  ```

- [ ] **Verify deployment**
  - [ ] Health check: `curl https://your-app.fly.dev/health`
  - [ ] Test query via web UI
  - [ ] Run smoke tests against deployed URL

## Portfolio Presentation Checklist

- [ ] **Repository**
  - [ ] Public GitHub repo created
  - [ ] All code pushed
  - [ ] `.env` is gitignored (not pushed)
  - [ ] README.md is complete and accurate
  - [ ] Architecture diagram included in `docs/`

- [ ] **Documentation**
  - [ ] README has clear setup instructions
  - [ ] Example queries included
  - [ ] API documentation mentioned
  - [ ] Troubleshooting guide available

- [ ] **Demo**
  - [ ] Live URL deployed (Fly.io or similar)
  - [ ] Live URL added to README
  - [ ] Screenshot of web UI in README (optional)
  - [ ] Demo video recorded (optional)

- [ ] **Code Quality**
  - [ ] Code is clean and well-structured
  - [ ] Comments added for complex logic
  - [ ] No hardcoded secrets
  - [ ] Error handling implemented
  - [ ] Logging in place

- [ ] **Portfolio Site**
  - [ ] Project added to portfolio
  - [ ] GitHub link included
  - [ ] Live demo link included
  - [ ] Tech stack highlighted
  - [ ] Learning outcomes mentioned

## Maintenance Checklist

### Regular Checks

- [ ] Monitor Fly.io credits/usage
- [ ] Check for API rate limit issues
- [ ] Review error logs periodically
- [ ] Test demo URL monthly

### Updates

- [ ] Update PDFs if new regulations released
- [ ] Re-run ingestion after PDF updates
- [ ] Update dependencies (security patches)
- [ ] Rebuild and redeploy after updates

### Improvements

- [ ] Add more eval questions over time
- [ ] Tune similarity_threshold based on usage
- [ ] Consider adding conversation history
- [ ] Explore hybrid search (keyword + semantic)

## Troubleshooting Reference

If anything fails, check:

1. `docker-compose logs api` for API errors
2. `docker-compose logs chroma` for vector store errors
3. `./run.sh health` for service status
4. `TROUBLESHOOTING.md` for common issues
5. Verify `.env` file has correct API key
6. Ensure all 6 PDFs are present in `PDFs/`

## Success Criteria

✅ Project is complete when:

1. Services start successfully
2. Ingestion completes without errors
3. Smoke tests pass
4. Eval suite achieves 10/10 success
5. Web UI works end-to-end
6. Live demo is deployed and accessible
7. GitHub repo is public with complete README
8. Portfolio entry is published with links

## Time Estimates

- Initial setup: 15-30 minutes
- First ingestion: 5-20 minutes
- Local testing: 30 minutes
- Cloud deployment: 30-45 minutes
- Documentation polish: 1-2 hours
- Total: 3-4 hours for complete setup

## Next Steps After Completion

1. Share demo with potential employers
2. Write blog post about implementation
3. Add to LinkedIn projects
4. Consider enhancements from README "Future Enhancements"
5. Gather feedback from users
6. Iterate on answer quality
