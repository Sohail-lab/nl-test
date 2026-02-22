import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import worker  # noqa: E402


def _item(label):
    return {
        'label_raw': label,
        'label_normalized': worker.normalize_sidebar_text(label),
        'is_visible': True,
        'has_expand_icon': False,
        'click_xpath': None,
    }


class SidebarNormalizationTests(unittest.TestCase):
    def test_normalize_configure_dropdown(self):
        self.assertEqual(
            worker.normalize_sidebar_text('Click on the Configure dropdown'),
            'configure'
        )

    def test_normalize_ampersand_entities(self):
        self.assertEqual(
            worker.normalize_sidebar_text('Challenge & Solicitation'),
            'challenge solicitation'
        )
        self.assertEqual(
            worker.normalize_sidebar_text('Challenge &amp; Solicitation'),
            'challenge solicitation'
        )

    def test_extract_sidebar_target(self):
        info = worker.extract_sidebar_target('Click on the Configure dropdown')
        self.assertTrue(info['is_sidebar_candidate'])
        self.assertEqual(info['normalized_target'], 'configure')


class SidebarMatchTests(unittest.TestCase):
    def test_exact_normalized_match(self):
        items = [_item('Configure'), _item('Reports')]
        result = worker.match_sidebar_item('Click on the Configure dropdown', items)
        self.assertTrue(result['ok'])
        self.assertEqual(result['matchTier'], 'exact-normalized')
        self.assertEqual(result['candidate']['label_raw'], 'Configure')

    def test_token_overlap_match(self):
        items = [_item('Private Credit Dashboard'), _item('Reports')]
        result = worker.match_sidebar_item('private dashboard credit', items)
        self.assertTrue(result['ok'])
        self.assertEqual(result['matchTier'], 'token-overlap')
        self.assertEqual(result['candidate']['label_raw'], 'Private Credit Dashboard')

    def test_fuzzy_match(self):
        items = [_item('Valuation Sandbox'), _item('Reports')]
        result = worker.match_sidebar_item('valution sandbox', items)
        self.assertTrue(result['ok'])
        self.assertEqual(result['matchTier'], 'fuzzy')
        self.assertEqual(result['candidate']['label_raw'], 'Valuation Sandbox')

    def test_ambiguous_match(self):
        items = [_item('Task Status'), _item('Task Setup')]
        result = worker.match_sidebar_item('task', items)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'ambiguous')
        self.assertGreaterEqual(len(result.get('topCandidates', [])), 2)

    def test_no_match(self):
        items = [_item('Reports'), _item('Configure')]
        result = worker.match_sidebar_item('non existent section', items)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'no_match')

    def test_contains_low_score_does_not_false_match(self):
        items = [_item('Configure')]
        result = worker.match_sidebar_item(
            'Select Configure and Click on Data Sources and Click on Pricing Data Source',
            items
        )
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'no_match')


class SidebarMenuIconSelectionTests(unittest.TestCase):
    def test_choose_visible_outside_drawer_icon(self):
        icons = [
            {'index': 0, 'is_visible': True, 'inside_drawer': True},
            {'index': 1, 'is_visible': True, 'inside_drawer': False},
        ]
        chosen = worker.choose_best_menu_icon(icons)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen['index'], 1)

    def test_xpath_generation_is_drawer_scoped(self):
        xpaths = worker.build_sidebar_click_xpaths('Challenge & Solicitation')
        self.assertTrue(xpaths)
        self.assertTrue(any('IvpLeftMenuDrawer' in xp or 'testDrawer' in xp for xp in xpaths))


class DecomposeHeuristicTests(unittest.TestCase):
    def test_multi_action_chain_is_split(self):
        step = 'Select Configure and Click on Data Sources and Click on Pricing Data Source'
        parts = worker.heuristic_decompose_step(step)
        self.assertEqual(
            parts,
            ['Select Configure', 'Click on Data Sources', 'Click on Pricing Data Source']
        )

    def test_non_chain_not_split(self):
        step = 'Click on the Next button'
        parts = worker.heuristic_decompose_step(step)
        self.assertEqual(parts, [step])


if __name__ == '__main__':
    unittest.main()
