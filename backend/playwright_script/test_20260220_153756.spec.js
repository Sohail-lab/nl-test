import { test, expect } from '@playwright/test';

test('Generated Test', async ({ page }) => {
    await page.goto(`https://srv-pricemqarearch.ivp.in/IVPEDM`);
    // step: Click on the email field
    // 2026-02-20 15:37:56 click
    await page.click(`xpath=//input[@id='username']`);
    // step: Enter "mdsohail@ivp.in" in the email field
    // 2026-02-20 15:38:00 fill
    await page.fill(`xpath=//input[@id='username']`, `mdsohail@ivp.in`);
    // step: Click on the instance dropdown
    // 2026-02-20 15:38:10 click
    await page.click(`xpath=//input[@id='client-dropdown']`);
    // step: Click on "pmqaautomationuat" option
    // 2026-02-20 15:38:21 click
    await page.click(`xpath=//div[@id='section-client']//div[normalize-space(text())='pmqaautomationuat']`);
    // step: Click on the Next button
    // 2026-02-20 15:38:28 click
    await page.click(`xpath=//input[@id='submit-button' and @type='submit' and @value='Next']`);
    // step: Click on the password field
    // 2026-02-20 15:38:37 click
    await page.click(`xpath=//input[@id='password']`);
    // step: Enter "ivp@123" in the password field
    // 2026-02-20 15:38:42 fill
    await page.fill(`xpath=//input[@id='password']`, `ivp@123`);
    // step: Click the submit button
    // 2026-02-20 15:38:49 click
    await page.click(`xpath=//input[@id='submit-button']`);
    // step: Click on the top left menu
    // 2026-02-20 15:38:56 click
    await page.click(`xpath=//*[@data-testid='menu-icon']`);
    // step: Click on Dataset Configuration
    // 2026-02-20 15:39:01 click
    await page.click(`xpath=//*[contains(@class,'IvpLeftMenuDrawer')]//div[@aria-label='Dataset Configuration']/ancestor::div[@role='button'][1]`);
    // step: Click on Data Dictionary
    // 2026-02-20 15:39:30 click
    await page.click(`xpath=//*[contains(@class,'IvpLeftMenuDrawer')]//div[@aria-label='Data Dictionary']/ancestor::div[@role='button'][1]`);
    // step: Click on the row with Actual Column name value as_of_date
    // 2026-02-20 15:40:02 click
    await page.click(`xpath=//div[@role='row' and .//div[@role='gridcell' and normalize-space(.)='as_of_date']]`);
});