import { test, expect } from '@playwright/test';

test('Generated Test', async ({ page }) => {
    await page.goto(`https://srv-pricemqarearch.ivp.in/IVPPriceMaster`);
    // step: Click on email field
    // 2026-02-20 12:00:21 click
    await page.click(`xpath=//input[@id='username']`);
    // step: Enter "mdsohail@ivp.in" in email field
    // 2026-02-20 12:00:27 fill
    await page.fill(`xpath=//input[@id='username']`, `mdsohail@ivp.in`);
    // step: Click on the instance dropdown
    // 2026-02-20 12:00:35 click
    await page.click(`xpath=//input[@id='client-dropdown']`);
    // step: Click on "pmqaautomationuat" option
    // 2026-02-20 12:00:42 click
    await page.click(`xpath=//div[normalize-space(text())='pmqaautomationuat']`);
    // step: Click on the Next button
    // 2026-02-20 12:00:49 click
    await page.click(`xpath=//input[@id='submit-button']`);
    // step: Click on the password field
    // 2026-02-20 12:00:55 click
    await page.click(`xpath=//input[@id='password']`);
    // step: Enter "ivp@123" in the password field
    // 2026-02-20 12:01:00 fill
    await page.fill(`xpath=//input[@id='password']`, `ivp@123`);
    // step: Click the submit button
    // 2026-02-20 12:01:08 click
    await page.click(`xpath=//input[@id='submit-button' and @type='submit']`);
    // step: Click on "Pricing Blotter" text element on top left
    // 2026-02-20 12:01:24 click
    await page.click(`xpath=//button[@id='tabControlTabName-IVPPriceMaster/Blotter']`);
    // step: Click on the menu icon on top left
    // 2026-02-20 12:01:53 click
    await page.click(`xpath=//*[@data-testid='menu-icon']`);
    // step: Click on Configure
    // 2026-02-20 12:01:59 click
    await page.click(`xpath=//div[@aria-label='Configure']/ancestor::div[@role='button']`);
    // step: Click on Data Sources
    // 2026-02-20 12:02:00 click
    await page.click(`xpath=//div[@aria-label='Data Sources']/ancestor::div[@role='button']`);
    // step: Click on Pricing Data Source
    // 2026-02-20 12:02:00 click
    await page.click(`xpath=//div[@aria-label='Pricing Data Source']/ancestor::div[@role='button']`);
    // step: Click on the plus button on the left of BROKER
    // 2026-02-20 12:02:11 click
    await page.click(`xpath=//div[@id='BROKER']//button[.//*[@data-testid='AddIcon']]`);
    // step: Click on the dropdown
    // 2026-02-20 12:02:24 click
    await page.click(`xpath=//button[@id='AddGroup']`);
    // step: Click on "Sohail DS" option
    // 2026-02-20 12:02:31 click
    await page.click(`xpath=//button[normalize-space(.)='Sohail DS' and contains(@class,'pm_ds_dataCardButton')]`);
    // step: Click on Save button
    // 2026-02-20 12:02:40 click
    await page.click(`xpath=//button[@data-testid='pm-ds-save-btn']`);
    // step: Click on Okay button
    // 2026-02-20 12:02:48 click
    await page.click(`xpath=//button[@data-testid='modal_okay_button']`);
    // step: Click on Back button
    // 2026-02-20 12:02:55 click
    await page.click(`xpath=//button[@data-testid='pm-ds-back-btn']`);
    // step: Click on Position on the top bar between Security and Pricing
    // 2026-02-20 12:03:08 click
    await page.click(`xpath=//button[@role='tab' and .//div[@aria-label='Position']]`);
    // step: Click on PositionDataSource
    // 2026-02-20 12:03:13 click
    await page.click(`xpath=//*[@role='tab'][.//text()[normalize-space(.)='PositionDataSource']]`);
    // step: Click on the menu icon on top left
    // 2026-02-20 12:03:21 click
    await page.click(`xpath=//*[@data-testid='menu-icon']`);
    // step: Click on the Configure dropdown
    // 2026-02-20 12:03:33 click
    await page.click(`xpath=//div[@aria-label='Configure']/ancestor::div[@role='button'][1]`);
    // step: Click on "Configure" option
    // 2026-02-20 12:03:45 click
    await page.click(`xpath=//div[@aria-label='Configure']/ancestor::div[@role='button' and contains(@class,'MuiListItemButton-root')]`);
});