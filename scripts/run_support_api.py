"""Run only the internal API; never import/start a Telegram polling process."""
import argparse
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--service-env-file', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8091)
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=False)
    load_dotenv(args.service_env_file, override=True)
    if len(os.getenv('RAG_SERVICE_TOKEN', '')) < 32:
        raise SystemExit('Configure RAG_SERVICE_TOKEN with at least 32 characters')
    from app.support_receipt import write_receipt
    write_receipt()
    import uvicorn
    uvicorn.run('app.api:app', host='127.0.0.1', port=args.port, workers=1, access_log=False)
