"""The unattended publisher wrapper (scripts/ops/pawstcard_publish.sh): its staging step must carry the Iris evidence.

publish_journal.py reads <queue>/reviews/<slug>.iris.json. The wrapper builds a staging copy of the queue (step 4); if that copy
does not include reviews/, every due post is held as "copy review missing". This test runs the real staging block of the script
(the lines from `STAGE=` up to `REPORT=`) against a temp queue and checks that the evidence arrives.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WRAPPER = REPO / "scripts" / "ops" / "pawstcard_publish.sh"


def staging_block(text):
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith('STAGE="$(mktemp -d'))
    end = next(i for i, l in enumerate(lines) if l.startswith("REPORT="))
    return "\n".join(lines[start:end])


class StagingCarriesIrisEvidence(unittest.TestCase):
    def test_stage_copies_manuscript_and_reviews(self):
        block = staging_block(WRAPPER.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            base, queue, work = Path(tmp, "base"), Path(tmp, "queue"), Path(tmp, "work")
            for d in (base, work, queue / "reviews"):
                d.mkdir(parents=True)
            (queue / "x.md").write_text("---\nslug: x\n---\nbody\n", encoding="utf-8")
            (queue / "reviews" / "x.iris.json").write_text('{"reviewer": "iris"}', encoding="utf-8")
            script = 'set -u\nBASE="$1"\nQUEUE="$2"\ncd "$3"\n' + block + '\necho "$STAGE"\n'
            env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
            out = subprocess.run(["bash", "-c", script, "wrapper-test", str(base), str(queue), str(work)],
                                 capture_output=True, text=True, env=env, check=True).stdout.strip().splitlines()
            stage = Path(out[-1])
            self.assertTrue((stage / "x.md").is_file(), "manuscript not staged")
            self.assertTrue((stage / "reviews" / "x.iris.json").is_file(),
                            "Iris evidence reviews/x.iris.json not carried into the staging queue")


if __name__ == "__main__":
    unittest.main()
