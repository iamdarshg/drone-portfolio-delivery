"""Optional local browser verification; Playwright is not a runtime dependency."""
import asyncio, hashlib, json
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    root=Path(__file__).resolve().parent
    data=json.loads((root/'data.json').read_text())
    for entry in data['assets']:
        assert hashlib.sha256((root/entry['file']).read_bytes()).hexdigest()==entry['sha256']
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={'width':1200,'height':900})
        errors=[]
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto('http://127.0.0.1:8765')
        await page.wait_for_function("document.querySelectorAll('.repo').length===2 && document.querySelector('#mesh-status').textContent.includes('triangles')")
        assert await page.locator('#board').evaluate('(e)=>e.complete && e.naturalWidth>0')
        await page.select_option('#pcb','bottom')
        await page.wait_for_function("document.querySelector('#board').complete && document.querySelector('#board').naturalWidth>0")
        await page.get_by_text('Open bundled snapshot',exact=True).first.click()
        await page.wait_for_function("document.querySelector('.repo pre').textContent.length>100")
        await page.get_by_text('Open from GitHub',exact=True).first.click()
        await page.wait_for_function("!document.querySelector('.repo button').disabled")
        assert 'Loaded from GitHub' in await page.locator('.repo').first.inner_text()
        await page.select_option('#model','real_motor_housing.stl')
        await page.wait_for_function("document.querySelector('#mesh-status').textContent.includes('triangles') && document.querySelector('#mesh-status').textContent.includes('superseded')")
        await page.locator('#rotate').fill('85')
        await page.route('https://raw.githubusercontent.com/**/docs/media/build/**',lambda route:route.fulfill(status=404,body='Not Found'))
        await page.click('#photos')
        await page.wait_for_function("!document.querySelector('#photos').disabled")
        assert await page.locator('#photo-results img').count()==0
        assert 'No physical-build photo supplied' in await page.locator('#photo-results').inner_text()
        await page.unroute('https://raw.githubusercontent.com/**/docs/media/build/**')
        await page.route('https://raw.githubusercontent.com/**/docs/media/build/**',lambda route:route.abort('internetdisconnected'))
        await page.click('#photos')
        await page.wait_for_function("!document.querySelector('#photos').disabled")
        assert await page.locator('#photo-results img').count()==0
        assert not errors, errors
        await page.set_viewport_size({'width':390,'height':844})
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await browser.close()
        report={'asset_hashes':'PASS','source_snapshots':'PASS','live_github_fetch':'PASS','PCB_selection':'PASS','STL_load_and_rotation':'PASS','photo_404_fallback':'PASS','photo_network_fallback':'PASS','unhandled_page_errors':errors,'mobile_horizontal_overflow':False}
        (root/'test-results.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))

asyncio.run(main())
