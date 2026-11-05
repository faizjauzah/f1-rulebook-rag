# Troubleshooting Guide

## Common Issues and Solutions

### 1. Docker Services Won't Start

**Issue**: `docker-compose up` fails or services crash

**Solutions**:
- Check if ports 8000 and 8001 are already in use:
  ```bash
  lsof -i :8000
  lsof -i :8001
  ```
- Kill conflicting processes or change ports in `docker-compose.yml`
- Check Docker has enough resources (4GB RAM minimum)
- View logs: `docker-compose logs`

### 2. ChromaDB Connection Errors

**Issue**: API can't connect to ChromaDB

**Solutions**:
- Wait for ChromaDB healthcheck to pass (check `docker-compose logs chroma`)
- Verify ChromaDB is running: `curl http://localhost:8001/api/v1/heartbeat`
- Restart services: `docker-compose restart`

### 3. Ingestion Fails

**Issue**: `/ingest` returns 500 error or times out

**Solutions**:
- **Check API key**: Verify `GOOGLE_API_KEY` in `.env` is correct
- **Rate limits**: Gemini free tier is 15 RPM. Wait and retry if hit
- **Timeout**: Ingestion takes 5-20 minutes. Don't close the terminal
- **Check logs**: `docker-compose logs api` for detailed errors
- **Verify PDFs**: Ensure all 6 PDFs are in `/PDFs/` directory

### 4. "Collection not found" Error

**Issue**: Queries fail with "Collection not found"

**Solution**: Run ingestion first:
```bash
curl -X POST http://localhost:8000/ingest
```

### 5. Local Mode Issues

**Issue**: Local profile doesn't work

**Solutions**:
- **LM Studio not running**: Start LM Studio server on port 1234
- **Model not loaded**: Load a model in LM Studio before querying
- **Wrong base_url**: From Docker, use `http://host.docker.internal:1234/v1`
- **Embeddings slow**: First run downloads bge-large model (~1.3GB)

### 6. No Results / Low Quality Answers

**Issue**: Queries return "no relevant regulations found" or poor answers

**Solutions**:
- **Lower threshold**: In `config.yaml`, reduce `similarity_threshold` from 0.6 to 0.4
- **Increase top_k**: Change `top_k` from 5 to 10 in `config.yaml`
- **Check question**: Ensure it's about F1 regulations, not general racing
- **Try different phrasing**: Rephrase using regulation terminology

### 7. Slow Response Times

**Issue**: Queries take >10 seconds

**Solutions**:
- **Gemini**: Check internet connection, may be regional latency
- **Local mode**: Ensure LM Studio model fits in RAM (8GB+ recommended)
- **Reduce top_k**: Fewer chunks = faster generation
- **Check resources**: Docker container CPU/RAM limits

### 8. Web UI Not Loading

**Issue**: http://localhost:8000 doesn't load

**Solutions**:
- Verify API is running: `curl http://localhost:8000/health`
- Check browser console for errors
- Try different browser or incognito mode
- Verify port forwarding if using remote Docker

### 9. Evaluation Script Fails

**Issue**: `python eval/run_eval.py` errors

**Solutions**:
- **Outside Docker**: Install dependencies `pip install requests`
- **Inside Docker**: `docker-compose exec api python eval/run_eval.py`
- **API not ready**: Check services are running and ingestion completed
- **Timeout**: Increase timeout in `run_eval.py` line 31

### 10. PDF Parsing Issues

**Issue**: Chunks don't match article structure

**Solutions**:
- PDFs must follow standard FIA format (Section X [Name])
- Check logs for "Extracted X chunks" per PDF
- Some articles may span multiple chunks (intentional for long articles)
- Verify PDF filenames match expected pattern

## Getting Help

1. **Check logs**: `docker-compose logs api` or `docker-compose logs chroma`
2. **Health check**: `curl http://localhost:8000/health`
3. **Test ChromaDB**: `curl http://localhost:8001/api/v1/heartbeat`
4. **Verify config**: Check `config.yaml` profile matches your setup
5. **Check .env**: Ensure `GOOGLE_API_KEY` is set and valid

## Debug Mode

Enable verbose logging:

1. Edit `app/main.py`, change:
   ```python
   logging.basicConfig(level=logging.DEBUG)
   ```

2. Rebuild:
   ```bash
   docker-compose up --build
   ```

3. View detailed logs:
   ```bash
   docker-compose logs -f api
   ```

## Reset Everything

If all else fails, clean slate:

```bash
./run.sh clean
# Or manually:
docker-compose down -v
rm -rf data/
docker-compose up --build
curl -X POST http://localhost:8000/ingest
```

## Performance Benchmarks

Expected performance on decent hardware:

- **Ingestion**: 5-20 min (Gemini slower due to rate limits)
- **Query response**: 2-5 seconds
- **Eval suite**: 5-10 minutes (10 questions)
- **Startup time**: 30-60 seconds (ChromaDB healthcheck)

Significantly outside these ranges indicates an issue.
