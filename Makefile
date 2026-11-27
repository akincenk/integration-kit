.PHONY: test run docker e2e
test:   ## Python + JavaScript tests
	uv run pytest -q && node --test sdk/js/index.test.mjs
run:    ## local server on :8000
	uv run uvicorn server.app:app --reload
docker: ## build and run the container
	docker build -t integration-kit:local . && docker run --rm -p 8000:8000 integration-kit:local
e2e:    ## kind cluster + Kubernetes deploy + SDK smoke test
	./k8s/kind-e2e.sh
