.PHONY: investigate-demo repair-demo eval eval-report api web

investigate-demo:
	bash scripts/dev/investigate_demo.sh

repair-demo:
	bash scripts/dev/repair_demo.sh

eval:
	python docsmith.py evaluate --suite curated --backend ollama --out evaluation/data/runs/curated.json

eval-report:
	python -c "from evaluation.report import load_run, render_table, update_readme; update_readme('README.md', render_table(load_run('evaluation/data/runs/curated.json')))"

api:
	uvicorn webapp.app:app --reload --port 8000

web:
	npm --prefix frontend run dev
