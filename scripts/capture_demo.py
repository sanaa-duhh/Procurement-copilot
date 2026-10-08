"""Exercise the local scripted UI and save screenshots; never calls a live model.

Start: uv run python run_local.py --demo --api-port 8003 --ui-port 8502
Run:   uv run --with playwright python scripts/capture_demo.py
"""
import argparse
import csv
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def check_layout(page):
    assert page.locator('[data-testid="stException"]').count() == 0
    assert not page.locator('[data-testid="stAppDeployButton"]').is_visible()
    assert not page.locator('[data-testid="stToolbar"]').is_visible()
    overflow = page.evaluate('''() => {
      const main = document.querySelector('[data-testid="stMain"]');
      return main.scrollWidth > main.clientWidth + 2;
    }''')
    assert not overflow, 'The workspace overflows horizontally'


def choose(page, label, option):
    control = page.get_by_role('combobox', name=label, exact=True)
    control.click()
    control.fill(option.split(' · ')[0])
    page.get_by_text(option, exact=True).click()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8502')
    parser.add_argument('--chrome', default='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    args = parser.parse_args()
    output = Path('docs/images')
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.chrome)
        page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
        page.goto(args.url)
        page.locator('.mode').filter(has_text='Scripted demo').wait_for(timeout=30000)
        page.get_by_role('button', name='Analyse request', exact=True).wait_for()
        check_layout(page)
        page.screenshot(path=str(output/'review-workspace.png'))
        choose(page, 'Choose a request', 'REQ-1007 · SignalWatch Advanced')
        page.get_by_role('button', name='Analyse request', exact=True).click()
        page.locator('.decision h2').filter(has_text='Manual review required').wait_for(timeout=30000)
        page.locator('.decision').scroll_into_view_if_needed()
        check_layout(page)
        page.screenshot(path=str(output/'demo-conflicting-vendor.png'))
        page.get_by_role('tab', name='Human review', exact=True).click()
        page.get_by_role('button', name='Save review', exact=True).click()
        page.get_by_text('Enter a reviewer name before saving.', exact=True).wait_for()
        for label, extension in [('Download handoff', 'md'), ('Download decision JSON', 'json')]:
            with page.expect_download() as event:
                page.get_by_role('button', name=label, exact=True).click()
            download = event.value
            text = Path(download.path()).read_text()
            assert 'REQ-1007' in text
            if extension == 'json':
                assert json.loads(text)['human_review_required'] is True
        page.get_by_role('tab', name='Compare architectures', exact=True).click()
        page.get_by_role('heading', name='Compare the architectures', exact=True).wait_for()
        assert '18/18' in page.locator('.compare-table').inner_text()
        page.get_by_role('heading', name='Compare the architectures', exact=True).scroll_into_view_if_needed()
        check_layout(page)
        page.screenshot(path=str(output/'architecture-comparison.png'))
        choose(page, 'Evaluation case', 'PUB-01 · Low-value approved vendor')
        page.get_by_role('button', name='Download comparison CSV', exact=True).wait_for()
        for label in ['Download comparison CSV', 'Download decision memo']:
            with page.expect_download() as event:
                page.get_by_role('button', name=label, exact=True).click()
            content = Path(event.value.path()).read_text()
            if label.endswith('CSV'):
                assert len(list(csv.DictReader(content.splitlines()))) == 36
            else:
                assert len(content.split()) <= 500
        page.get_by_role('tab', name='Review a request', exact=True).click()
        page.get_by_role('radiogroup', name='Analysis approach', exact=True).get_by_text('Analyst + reviewer', exact=True).click()
        page.get_by_role('button', name='Analyse request', exact=True).click()
        page.locator('.decision h2').filter(has_text='Manual review required').wait_for()
        page.get_by_role('tab', name='Run details', exact=True).click()
        page.get_by_text('Analyst-to-reviewer handoff', exact=True).click()
        page.get_by_role('radiogroup', name='Analysis approach', exact=True).get_by_text('Single agent', exact=True).click()
        page.get_by_text('New request', exact=True).click()
        page.get_by_role('textbox', name='Product or service', exact=True).fill('<img id="injected-product" src=x>')
        page.get_by_role('textbox', name='Vendor', exact=True).fill('Example vendor')
        page.get_by_role('button', name='Analyse request', exact=True).click()
        page.locator('.decision h2').filter(has_text='More information needed').wait_for()
        assert page.locator('#injected-product').count() == 0
        page.set_viewport_size({'width': 390, 'height': 844})
        page.get_by_role('textbox', name='Product or service', exact=True).wait_for(state='hidden')
        check_layout(page)
        # Save a clean intake screenshot after the malformed-input check.
        page.goto(args.url)
        page.locator('.mode').filter(has_text='Scripted demo').wait_for(timeout=30000)
        page.get_by_role('button', name='Analyse request', exact=True).wait_for()
        check_layout(page)
        page.screenshot(path=str(output/'review-mobile.png'))
        page.get_by_role('tab', name='Compare architectures', exact=True).click()
        page.get_by_role('heading', name='Compare the architectures', exact=True).wait_for()
        check_layout(page)
        print('Browser checks passed: toolbar, layout, both architectures, review validation, four downloads, comparison browsing, new request, HTML escaping and mobile width in both views.')
        browser.close()


if __name__ == '__main__':
    main()
