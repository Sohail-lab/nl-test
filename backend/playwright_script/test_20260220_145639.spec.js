import { test, expect } from '@playwright/test';

test('Generated Test', async ({ page }) => {
    await page.goto(`https://srv-pricemqarearch.ivp.in/IVPPriceMaster`);
    // step: Click on email field
    // 2026-02-20 14:56:39 click
    await page.click(`xpath=//input[@id='username']`);
    // step: Enter "mdsohail@ivp.in" in email field
    // 2026-02-20 14:56:44 fill
    await page.fill(`xpath=//input[@id='username']`, `mdsohail@ivp.in`);
    // step: Click on the instance dropdown
    // 2026-02-20 14:56:52 click
    await page.click(`xpath=//input[@id='client-dropdown']`);
    // step: Click on "pmqaautomationuat" option
    // 2026-02-20 14:56:58 click
    await page.click(`xpath=//div[@id='section-client']//div[normalize-space(text())='pmqaautomationuat']`);
    // step: Click on the Next button
    // 2026-02-20 14:57:06 click
    await page.click(`xpath=//input[@id='submit-button' and @type='submit' and @value='Next']`);
    // step: Click on password field
    // 2026-02-20 14:57:15 click
    await page.click(`xpath=//input[@id='password']`);
    // step: Enter "ivp@123" in password field
    // 2026-02-20 14:57:19 fill
    await page.fill(`xpath=//input[@id='password']`, `ivp@123`);
    // step: Click on submit button
    // 2026-02-20 14:57:28 click
    await page.click(`xpath=//input[@id='submit-button']`);
});