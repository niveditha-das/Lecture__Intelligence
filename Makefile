.PHONY: up down logs test psql eval eval-ablation eval-history export-goldset

up:              ## start postgres + api
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api

test:
	cd backend && python -m pytest tests -q

psql:
	docker compose exec db psql -U lia -d lia

eval:            ## full suite: retrieval + generation + grounding, persisted
	cd backend && python -m app.evaluation.runner --label "hybrid+rerank"

eval-ablation:   ## the comparison that goes in the README
	cd backend && python -m app.evaluation.runner --label "no rerank" --no-rerank --retrieval-only
	cd backend && python -m app.evaluation.runner --label "rerank"    --retrieval-only

eval-history:    ## every run ever, newest first
	curl -s localhost:8000/eval/runs | python3 -m json.tool

export-goldset:  ## make the eval set portable across databases
	cd backend && python -m app.evaluation.seed --export --out evalsets/goldset.jsonl
