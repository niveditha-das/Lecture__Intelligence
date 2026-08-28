.PHONY: up down logs test eval eval-ablation psql

up:            ## start postgres + api
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api

test:
	docker compose exec api python -m pytest tests -q

psql:
	docker compose exec db psql -U lia -d lia

eval:          ## full suite: retrieval + generation + grounding
	docker compose exec api python -m app.evaluation.runner --label "hybrid+rerank" --k 5

eval-ablation: ## the comparison that goes in the README
	docker compose exec api python -m app.evaluation.runner --label "vector+kw, no rerank" --no-rerank --retrieval-only --k 5
	docker compose exec api python -m app.evaluation.runner --label "vector+kw, rerank"    --retrieval-only --k 5
