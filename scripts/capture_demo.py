"""Exercise the local scripted UI and save screenshots; never calls a live model.

Start: uv run python run_local.py --demo --api-port 8003 --ui-port 8502
Run:   uv run --with playwright python scripts/capture_demo.py
"""
import argparse
import csv
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def wait_idle(page):
    page.locator('[data-testid="stApp"][data-test-script-state="notRunning"]').wait_for()


def check_layout(page):
    wait_idle(page)
    assert page.locator('[data-testid="stException"]').count() == 0
    assert not page.locator('[data-testid="stAppDeployButton"]').is_visible()
    assert not page.locator('[data-testid="stToolbar"]').is_visible()
    overflow = page.evaluate('''() => {
      const main = document.querySelector('[data-testid="stMain"]');
      return main.scrollWidth > main.clientWidth + 2;
    }''')
    if overflow:
        page.screenshot(path='/tmp/procurement-overflow.png', animations='disabled')
        protruding = page.evaluate('''() => [...document.querySelectorAll('[data-testid="stMain"] *')]
          .filter(e => e.getBoundingClientRect().right > innerWidth + 2 && e.getBoundingClientRect().width > 0)
          .slice(0, 8).map(e => ({tag:e.tagName, testid:e.dataset.testid, class:e.className,
            right:e.getBoundingClientRect().right, text:e.textContent.slice(0,80)}))''')
        raise AssertionError(f'The workspace overflows horizontally: {protruding}')


def choose(page, label, option):
    wait_idle(page)
    control = page.get_by_role('combobox', name=label, exact=True)
    control.click()
    control.fill(option.split(' · ')[0])
    page.get_by_role('option', name=option, exact=True).click()
    wait_idle(page)


def set_theme(page, theme):
    wait_idle(page)
    toggle = page.get_by_role('switch', name='Light mode', exact=True)
    if toggle.is_checked() != (theme == 'light'):
        page.get_by_text('Light mode', exact=True).click()
    page.wait_for_function('(theme) => getComputedStyle(document.documentElement).colorScheme === theme', arg=theme)
    wait_idle(page)


def check_field_contrast(page):
    # Sample the actual rendered control; catches native fields keeping the old palette.
    ratio = page.get_by_role('combobox').first.evaluate('''e => {
      const luminance = colour => {
        const rgb = colour.match(/[\\d.]+/g).slice(0,3).map(Number).map(c => {
          const s = c / 255; return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4;
        });
        return .2126*rgb[0] + .7152*rgb[1] + .0722*rgb[2];
      };
      const fg = luminance(getComputedStyle(e).color);
      const bg = luminance(getComputedStyle(e.parentElement).backgroundColor);
      return (Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05);
    }''')
    assert ratio >= 4.5, f'Selectbox text contrast is too low: {ratio:.2f}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8502')
    parser.add_argument('--chrome', default='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    parser.add_argument('--theme', choices=['dark', 'light'], default='dark')
    args = parser.parse_args()
    output = Path('docs/images')
    output.mkdir(parents=True, exist_ok=True)
    suffix = '-light' if args.theme == 'light' else ''
    def capture(page, name):
        wait_idle(page)
        page.screenshot(path=str(output/f'{name}{suffix}.png'), animations='disabled')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.chrome)
        page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
        page.goto(args.url)
        page.locator('.mode').filter(has_text='Scripted demo').wait_for(timeout=30000)
        page.get_by_role('button', name='Analyse request', exact=True).wait_for()
        set_theme(page, args.theme)
        # The native switch must also work from the keyboard.
        toggle = page.get_by_role('switch', name='Light mode', exact=True)
        toggle.focus()
        toggle.press('Space')
        opposite = 'light' if args.theme == 'dark' else 'dark'
        page.wait_for_function('(theme) => getComputedStyle(document.documentElement).colorScheme === theme', arg=opposite)
        assert toggle.is_checked() == (opposite == 'light')
        set_theme(page, args.theme)
        page.reload()
        page.get_by_role('button', name='Analyse request', exact=True).wait_for()
        assert page.get_by_role('switch', name='Light mode', exact=True).is_checked() == (args.theme == 'light')
        check_field_contrast(page)
        check_layout(page)
        capture(page, 'review-workspace')
        choose(page, 'Choose a request', 'REQ-1007 · SignalWatch Advanced')
        page.get_by_role('button', name='Analyse request', exact=True).click()
        page.locator('.decision h2').filter(has_text='Manual review required').wait_for(timeout=30000)
        page.locator('.decision').scroll_into_view_if_needed()
        check_layout(page)
        set_theme(page, 'light' if args.theme == 'dark' else 'dark')
        page.locator('.decision h2').filter(has_text='Manual review required').wait_for()
        set_theme(page, args.theme)
        capture(page, 'demo-conflicting-vendor')
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
                original_run = json.loads(text)['run_id']
        # Reopen the exact persisted result after a new browser session.
        page.reload()
        page.get_by_role('button', name='Analyse request', exact=True).wait_for()
        choose(page, 'Choose a request', 'REQ-1007 · SignalWatch Advanced')
        saved = page.get_by_role('combobox', name='Saved analysis', exact=True)
        saved.click()
        saved.fill(original_run[:8])
        page.get_by_role('option').filter(has_text=original_run[:8]).click()
        page.get_by_role('button', name='View saved analysis', exact=True).click()
        page.locator('.decision h2').filter(has_text='Manual review required').wait_for()
        with page.expect_download() as event:
            page.get_by_role('button', name='Download decision JSON', exact=True).click()
        assert json.loads(Path(event.value.path()).read_text())['run_id'] == original_run
        page.get_by_role('tab', name='Compare architectures', exact=True).click()
        page.get_by_role('heading', name='Compare the architectures', exact=True).wait_for()
        page.locator('.st-key-compare_request button').click()
        current = page.get_by_role('tabpanel', name='This request', exact=True)
        current.get_by_role('button', name='Download this comparison', exact=True).wait_for()
        wait_idle(page)
        with page.expect_download() as event:
            current.get_by_role('button', name='Download this comparison', exact=True).click()
        comparison = json.loads(Path(event.value.path()).read_text())
        assert set(comparison['runs']) == {'single', 'staged'}
        assert all(comparison['runs'].values())
        assert comparison['request']['request_id'] == 'REQ-1007'
        current.locator('.compare-table').scroll_into_view_if_needed()
        check_layout(page)
        capture(page, 'request-comparison')
        page.get_by_role('tab', name='18-case benchmark', exact=True).click()
        benchmark = page.get_by_role('tabpanel', name='18-case benchmark', exact=True)
        assert '18/18' in benchmark.locator('.compare-table').inner_text()
        page.get_by_role('heading', name='Compare the architectures', exact=True).scroll_into_view_if_needed()
        benchmark.locator('.compare-table').scroll_into_view_if_needed()
        check_layout(page)
        capture(page, 'architecture-comparison')
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
        page.get_by_role('textbox', name='Requester name', exact=True).fill('Sanaa Newperson')
        page.get_by_role('textbox', name='Product or service', exact=True).wait_for()
        wait_idle(page)
        page.screenshot(path=f'/tmp/procurement-form-{args.theme}.png', animations='disabled')
        page.get_by_role('textbox', name='Product or service', exact=True).fill('<img id="injected-product" src=x>')
        page.get_by_role('textbox', name='Vendor', exact=True).fill('Example vendor')
        page.get_by_role('button', name='Analyse request', exact=True).click()
        page.locator('.decision h2').filter(has_text='More information needed').wait_for()
        assert page.locator('#injected-product').count() == 0
        page.get_by_text('Saved request', exact=True).click()
        page.get_by_role('combobox', name='Saved request', exact=True).wait_for()
        wait_idle(page)
        if not page.get_by_role('button', name='View saved analysis', exact=True).is_visible():
            page.locator('[data-testid="stExpander"]').filter(has=page.get_by_role('button', name='View saved analysis', exact=True, include_hidden=True)).locator('summary').click()
        page.get_by_role('button', name='View saved analysis', exact=True).click()
        page.locator('.decision h2').filter(has_text='More information needed').wait_for()
        if not page.locator('.request-card').is_visible():
            page.get_by_text('Request details', exact=True).click()
        assert 'Sanaa Newperson' in page.locator('.request-card').inner_text()
        assert page.locator('#injected-product').count() == 0
        page.set_viewport_size({'width': 390, 'height': 844})
        check_layout(page)
        # Save a clean intake screenshot after the malformed-input check.
        page.goto(args.url)
        page.locator('.mode').filter(has_text='Scripted demo').wait_for(timeout=30000)
        page.get_by_role('button', name='Analyse request', exact=True).wait_for()
        set_theme(page, args.theme)
        check_field_contrast(page)
        check_layout(page)
        capture(page, 'review-mobile')
        page.get_by_role('tab', name='Compare architectures', exact=True).click()
        page.get_by_role('heading', name='Compare the architectures', exact=True).wait_for()
        check_layout(page)
        page.get_by_role('tab', name='18-case benchmark', exact=True).click()
        check_layout(page)
        print(f'Browser checks passed ({args.theme}): history after refresh, request comparison, typed requester, five downloads, review validation, theme/keyboard persistence, input contrast, HTML escaping and mobile layouts.')
        browser.close()


if __name__ == '__main__':
    main()
