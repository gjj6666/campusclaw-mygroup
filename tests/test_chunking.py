import unittest

from campusclaw.chunking import split_text


class ChunkingTests(unittest.TestCase):
    def test_paragraphs_and_chinese_positions(self):
        text = "  第一段讲义。\n\n第二段 lesson content。  "
        chunks = split_text(text, size=16, overlap=3)
        self.assertTrue(chunks)
        self.assertEqual([chunk.ordinal for chunk in chunks], list(range(len(chunks))))
        self.assertTrue(all(text[c.char_start:c.char_end] == c.content for c in chunks))
        self.assertIn("第一段讲义。", [chunk.content for chunk in chunks])

    def test_long_paragraph_overlap_is_reproducible(self):
        text = "abcdefghij"
        chunks = split_text(text, size=6, overlap=2)
        self.assertEqual([(c.char_start, c.char_end, c.content) for c in chunks],
                         [(0, 6, "abcdef"), (4, 10, "efghij")])
        self.assertEqual(chunks, split_text(text, size=6, overlap=2))

    def test_empty_and_bad_configuration(self):
        self.assertEqual(split_text(" \n\n  "), [])
        with self.assertRaises(ValueError):
            split_text("text", size=5, overlap=5)


if __name__ == "__main__":
    unittest.main()
