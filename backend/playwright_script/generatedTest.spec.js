import { test, expect } from '@playwright/test';

test('Generated Test', async ({ page }) => {

    await page.goto('https://srv-pricemqarearch.ivp.in/IVPPriceMaster');

    // 2026-02-13 12:43:21 click
    await page.click(`xpath=//input[@id='username']`);

    // 2026-02-13 12:43:29 fill
    await page.fill(`xpath=//input[@id='username']`, `mdsohail@ivp.in`);

    // 2026-02-13 12:43:36 click
    await page.click(`xpath=//input[@id='client-dropdown']`);

    // 2026-02-13 12:43:45 click
    await page.click(`xpath=//div[@id='section-client']//div[@class='MuiBox-root css-1vcgz62' and normalize-space(.)='pmqaautomationuat']`);

    // 2026-02-13 12:43:49 click
    await page.click(`xpath=//input[@id='submit-button']`);

    // 2026-02-13 12:43:55 click
    await page.click(`xpath=//input[@id='password']`);

    // 2026-02-13 12:43:59 fill
    await page.fill(`xpath=//input[@id='password']`, `ivp@123`);

    // 2026-02-13 12:44:04 click
    await page.click(`xpath=//input[@id='submit-button']`);

    // 2026-02-13 12:44:21 click
    await page.click(`xpath=//button[@id='tabControlTabName-IVPPriceMaster/Blotter']`);

    // 2026-02-13 12:44:52 click
    await page.click(`xpath=//*[@data-testid='menu-icon']`);

    // 2026-02-13 12:45:08 click
    await page.click(`xpath=//div[@data-testid='pm_date_calendar']//button[.//*[@data-testid='CalendarMonthIcon']]`);

    // 2026-02-13 12:45:19 click
    await page.click(`xpath=//button[@aria-label='calendar view is open, switch to year view']`);

    // 2026-02-13 12:45:29 click
    await page.click(`xpath=//div[@role='dialog']//div[@role='radiogroup']//button[normalize-space(.)='2025']`);

    // 2026-02-13 12:45:38 click
    await page.click(`xpath=//button[@role='radio' and @aria-label='February']`);

    // 2026-02-13 12:45:59 click
    await page.click(`xpath=//div[contains(@class,'MuiDateCalendar-root')]//button[@role='gridcell' and normalize-space(.)='28' and not(contains(@class,'dayOutsideMonth'))]`);

    // 2026-02-13 12:46:23 click
    await page.click(`xpath=//div[@data-testid='user-details']//p[@aria-label='pmqaautomationuat']`);

    // 2026-02-13 12:46:34 click
    await page.click(`xpath=//div[@data-testid='userCard']//button[@title='Sign out']`);

});
