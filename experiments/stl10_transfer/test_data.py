import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from experiments.stl10_transfer import data
from experiments.public_scaling.config import Config


def fixture_cfg():
    return Config(dimensions=(32, 64), public_pool=128, samples=32, train_limit=384,
                  test_limit=64, pretrain_epochs=1, pretrain_batch=16, feature_batch=32,
                  prepare_threads=1, classes=10, kmeans_restarts=1, kmeans_max_iter=5)


class STLDataTests(unittest.TestCase):
    def test_torchvision_transpose_and_exact_area_mean(self):
        with tempfile.TemporaryDirectory() as td:
            raw = np.zeros((1, 3, 96, 96), dtype=np.uint8)
            raw[0, 0, 2, 5] = 255
            raw[0, 1, 3:6, 6:9] = 90
            path = Path(td) / "train_X.bin"
            path.write_bytes(raw.tobytes())
            loaded = data.read_images(path)
            self.assertEqual(loaded.shape, (1, 3, 96, 96))
            self.assertEqual(loaded[0, 0, 5, 2], 255)
            self.assertEqual(loaded[0, 0, 2, 5], 0)
            small = data.resize_area32(loaded)
            self.assertEqual(small.dtype, np.float32)
            self.assertEqual(small.shape, (1, 3072))
            self.assertTrue(np.isclose(small[0, 32], np.float32(1 / 9)))
            self.assertTrue(np.isclose(small[0, 1024 + 2 * 32 + 1], np.float32(90 / 255)))

    def test_fixture_prepare_partition_verify_and_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); cfg = fixture_cfg(); data.create_fixture(root / "source")
            out = data.prepare(root / "cache", root / "source", cfg, 77, "dirichlet_0.1", fixture=True)
            meta = json.loads((out / "prepared.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["dataset"], "STL-10 fixture")
            self.assertTrue(data.verify(out, cfg, 77, "dirichlet_0.1", fixture=True))
            self.assertEqual(np.load(out / "client_0_private.npy", mmap_mode="r").shape, (128, 32))
            self.assertEqual(np.load(out / "client_1_test.npy", mmap_mode="r").shape, (64, 64))
            public = np.load(out / "public_ids.npy")
            clients = [np.load(out / f"client_{i}_private_ids.npy") for i in range(2)]
            self.assertEqual(len(np.unique(public)), 128)
            self.assertEqual([len(x) for x in clients], [128, 128])
            self.assertEqual(len(np.unique(np.concatenate(clients))), 256)
            with (out / "client_0_private.npy").open("ab") as f:
                f.write(b"tamper")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                data.verify(out, cfg, 77, "dirichlet_0.1", fixture=True)


if __name__ == "__main__":
    unittest.main()
