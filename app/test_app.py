import asyncio, datetime as dt, json, os, tempfile, threading, time, urllib.request
from pathlib import Path
from unittest.mock import patch
import serve
from playwright.async_api import async_playwright

async def main():
    checks={}
    assert not serve.expired(dt.datetime(2027,9,30,tzinfo=dt.timezone.utc))
    assert serve.expired(dt.datetime(2027,10,1,tzinfo=dt.timezone.utc))
    with patch.object(serve,'expired',return_value=True):
        try:serve.run(0)
        except SystemExit:checks['expiry_startup']='PASS'
        else:raise AssertionError('Expiry allowed startup')
    with tempfile.TemporaryDirectory() as folder, patch.object(serve,'CACHE',Path(folder)),patch.object(serve,'remote',side_effect=OSError('offline')):
        result=serve.snapshot('drone-arm',True);assert result['origin']=='bundled'
        path=Path(folder)/'drone-arm.json';path.write_text(json.dumps(result))
        assert serve.snapshot('drone-arm',True)['origin']=='cached'
        checks['offline_metadata_fallback']='PASS'
    for name in ['drone-arm','drone-mech']:
        with urllib.request.urlopen('http://127.0.0.1:8766/api/snapshot?repo='+name+'&refresh=1',timeout=40) as r:
            result=json.load(r);assert len(result['commit'])==40 and result['tree']
            checks[name+'_API']=result['origin']
    async with async_playwright() as p:
        browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.route('https://raw.githubusercontent.com/**/docs/media/build/**',lambda r:r.fulfill(status=404,body='missing'))
        await page.goto('http://127.0.0.1:8766');await page.wait_for_function("document.querySelectorAll('.repo').length===2 && [...document.querySelectorAll('.document')].every(e=>e.textContent.length>100)",timeout=60000)
        assert await page.locator('.document h1,.document h2').count()>0
        assert await page.locator('.file-tree button').count()>5
        await page.wait_for_function("document.querySelector('#mesh-status').textContent.includes('triangles')")
        assert await page.locator('#mesh').is_visible();assert not await page.locator('#photo-results').is_visible()
        await page.select_option('#model','real_motor_bell.stl');await page.wait_for_function("document.querySelector('#mesh-status').textContent.includes('triangles')")
        await page.get_by_role('button',name='Reset view',exact=True).click()
        await page.locator('.file-tree input').first.fill('cli.py');await page.locator('.file-tree button').filter(has_text='engineering_acceptance/cli.py').first.click();await page.wait_for_function("document.querySelector('.document .keyword')!==null")
        checks['explorer_markdown_code_CAD']='PASS'
        output=Path(os.environ.get('APP_TEST_OUTPUT','E:/OneLine_final_media/app'));output.mkdir(parents=True,exist_ok=True)
        await page.screenshot(path=str(output/'desktop.png'),full_page=True)
        await page.set_viewport_size({'width':390,'height':844});assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth');await page.screenshot(path=str(output/'mobile.png'),full_page=True)
        await page.route('**/assets/*.stl',lambda r:r.fulfill(status=404,body='missing'));await page.select_option('#model','real_motor_housing.stl');await page.wait_for_function("document.querySelector('#mesh-status').textContent.includes('unavailable')");assert not await page.locator('#mesh').is_visible()
        await page.route('**/assets/esc_final_bottom.png',lambda r:r.abort());await page.select_option('#pcb','bottom');await page.wait_for_function("document.querySelector('#board').closest('section').hidden")
        checks['failed_media_sections_hidden']='PASS'
        await page.route('https://raw.githubusercontent.com/**/docs/media/build/**',lambda r:r.abort());await page.evaluate('loadPhotos()');assert not await page.locator('#photo-results').is_visible()
        checks['photo_404_offline_hidden']='PASS';assert not errors,errors;checks['unhandled_errors']=errors
        await page.emulate_media(reduced_motion='reduce');assert await page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
        await browser.close()
    Path('app-test-results.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2))
asyncio.run(main())
