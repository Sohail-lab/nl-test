import { test, expect } from '@playwright/test';

test('Generated Test', async ({ page }) => {
    await page.goto(`https://srv-pricemqarearch.ivp.in/IVPPriceMaster`);
    // 2026-02-18 12:02:10 click
    await page.click(`xpath=//input[@id='username']`);
    // 2026-02-18 12:02:15 fill
    await page.fill(`xpath=//input[@id='username']`, `mdsohail@ivp.in`);
    // 2026-02-18 12:02:23 click
    await page.click(`xpath=//input[@id='client-dropdown']`);
    // 2026-02-18 12:02:30 click
    await page.click(`xpath=//div[@id='section-client']//div[normalize-space(text())='pmqaautomationuat']`);
    // 2026-02-18 12:02:36 click
    await page.click(`xpath=//input[@id='submit-button']`);
    // 2026-02-18 12:02:45 click
    await page.click(`xpath=//input[@id='password']`);
    // 2026-02-18 12:02:50 fill
    await page.fill(`xpath=//input[@id='password']`, `ivp@123`);
    // 2026-02-18 12:02:59 click
    await page.click(`xpath=//input[@id='submit-button']`);
    // 2026-02-18 12:03:16 click
    await page.click(`xpath=//button[@role='tab' and .//div[@aria-label='Pricing Blotter']]`);
    // 2026-02-18 12:03:44 click
    await page.click(`xpath=//*[@data-testid='menu-icon']`);
});