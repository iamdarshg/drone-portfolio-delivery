import asyncio,json,urllib.request
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1200,'height':900});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto('http://127.0.0.1:8767');await page.wait_for_function("document.querySelectorAll('.repo').length===2 && [...document.querySelectorAll('.document')].every(e=>e.textContent.length>100)",timeout=60000)
        await page.wait_for_function("document.querySelectorAll('[data-path=hardware]').length>=1")
        reports={}
        for name,folders,path in [('drone-arm',['docs','docs/hardware'],'docs/hardware/VALIDATION_MATRIX.md'),('drone-mech',['highspeed_edf','highspeed_edf/deliverables','highspeed_edf/deliverables/phase15_geometry','highspeed_edf/deliverables/phase15_geometry/reports'],'highspeed_edf/deliverables/phase15_geometry/reports/phase15_geometry_manufacturing_report.md')]:
            box=page.locator('.repo').filter(has=page.get_by_role('heading',name=name,exact=True))
            for folder in folders:
                button=box.locator('button[data-path="'+folder+'"]');await button.wait_for();await button.click()
            file=box.locator('button[data-path="'+path+'"]');await file.wait_for();await file.click();await page.wait_for_function("([name,path])=>[...document.querySelectorAll('.repo')].find(e=>e.querySelector('h3').textContent===name).querySelector('.editor>p').textContent.includes(path)",arg=[name,path])
            await box.locator('.file-tree input').fill('README.md');assert await box.locator('.file-tree button').count()>0;await box.locator('.file-tree input').fill('')
            root=box.locator('button[data-path="'+folders[0]+'"]');await root.focus();await page.keyboard.press('ArrowRight');assert await root.get_attribute('aria-expanded')=='true';await page.keyboard.press('ArrowLeft');assert await root.get_attribute('aria-expanded')=='false'
            reports[name]='folder hierarchy, nested Markdown, search, keyboard PASS'
        arm=page.locator('.repo').first;await arm.locator('button[data-path="hardware"]').click();assert await arm.locator('button[data-path="hardware/esc"]').count()>0
        await page.set_viewport_size({'width':390,'height':844});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors;reports['unhandled_errors']=errors
        await browser.close()
    with urllib.request.urlopen('http://127.0.0.1:8767/api/snapshot?repo=drone-arm') as r:commit=json.load(r)['commit']
    with urllib.request.urlopen('http://127.0.0.1:8767/api/directory?repo=drone-arm&commit='+commit+'&path=docs') as r:assert json.load(r)['entries']
    reports['bounded_directory_endpoint']='PASS'
    Path('tree-test-results.json').write_text(json.dumps(reports,indent=2));print(json.dumps(reports,indent=2))
asyncio.run(main())
