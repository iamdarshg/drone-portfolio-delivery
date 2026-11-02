import asyncio,json,shutil
from pathlib import Path
from playwright.async_api import async_playwright
from PIL import Image

async def main():
    output=Path('<SOURCE_CHECKOUT>');output.mkdir(parents=True,exist_ok=True)
    raw=Path('E:/OneLine_final_media/showcase-review');raw.mkdir(parents=True,exist_ok=True)
    records=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
        await page.goto('http://127.0.0.1:8767');await page.wait_for_function("document.querySelectorAll('.repo').length===2 && [...document.querySelectorAll('.document')].every(e=>e.textContent.length>100)",timeout=60000)
        await page.wait_for_function("document.querySelector('#mesh-status').textContent.includes('triangles')")
        async def save(name,caption,locator=None):
            path=raw/name
            if locator:await locator.screenshot(path=str(path))
            else:await page.screenshot(path=str(path))
            shutil.copyfile(path,output/name)
            with Image.open(path) as image:size=list(image.size)
            records.append({'file':name,'dimensions':size,'caption':caption,'url':'http://127.0.0.1:8767'})
        await save('01-project-overview.png','Drone engineering overview with live repository workspace.')
        arm=page.locator('.repo').first
        await arm.locator('button[data-path="docs"]').click();await arm.locator('button[data-path="docs/hardware"]').click();await arm.locator('button[data-path="docs/hardware/VALIDATION_MATRIX.md"]').click()
        await page.wait_for_function("document.querySelector('.repo .editor>p').textContent.includes('VALIDATION_MATRIX.md')")
        await save('02-folders-and-markdown.png','Expanded docs/hardware hierarchy and formatted validation-matrix Markdown.',arm)
        await arm.locator('.file-tree input').fill('engineering_acceptance/cli.py');await arm.locator('.file-tree button').filter(has_text='engineering_acceptance/cli.py').click();await page.wait_for_function("document.querySelector('.repo .document .keyword')!==null")
        await save('03-source-workspace.png','Read-only engineering_acceptance/cli.py source with syntax coloring and file tab.',arm)
        mech=page.locator('.repo').nth(1);await save('04-mechanical-readme.png','Drone-mech folder hierarchy and automatically rendered repository README.',mech)
        await save('05-pcb-render.png','Actual ESC revision-B top CAD render; fabrication release blocked.',page.locator('#board').locator('xpath=ancestor::section'))
        await page.select_option('#model','duct_A_rotor_R1_N13.stl');await page.wait_for_function("document.querySelector('#mesh-status').textContent.includes('triangles')");await page.locator('#rotate').fill('55');await save('06-rotor-cad.png','Actual source-derived Phase-15 rotor STL wireframe with rotation, tilt and zoom controls.',page.locator('#mesh').locator('xpath=ancestor::section'))
        await page.set_viewport_size({'width':390,'height':844});await page.evaluate('scrollTo(0,0)');await save('07-mobile-overview.png','390-pixel mobile layout of the same local app.')
        await browser.close()
    (output/'captions.json').write_text(json.dumps(records,indent=2))
    print(json.dumps(records,indent=2))
asyncio.run(main())
