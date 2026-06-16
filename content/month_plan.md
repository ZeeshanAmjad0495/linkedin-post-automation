# One month of LinkedIn posts

Posted one per day, never repeated.

## Day 1 — 2026-06-16 — Test Automation

**Stop Sleeping in Your Playwright Tests**

Most flaky Playwright tests I inherit are flaky because someone waits on the wrong thing. They sleep for a fixed time, or wait for an element to be visible, then assert on data that has not loaded yet.

Here is the pattern I see over and over:

  await page.click("text=Refresh")
  await page.waitForTimeout(2000)
  const total = await page.textContent(".cart-total")
  expect(total).toBe("$240.00")

That waitForTimeout is a guess. On a fast CI run it wastes two seconds. On a slow one it fails because the network call took longer. Either way you learn nothing about the app.

Instead, wait for the thing that proves the state is ready. Usually that is the network response, not a pixel on screen.

  const refresh = page.waitForResponse(
    r => r.url().includes("/api/cart") && r.status() === 200
  )
  await page.click("text=Refresh")
  await refresh
  await expect(page.locator(".cart-total")).toHaveText("$240.00")

Two things changed. I tie the wait to the request the click triggers, so the test moves on the moment the data is back. And toHaveText retries, instead of reading text once, so a late render does not lose the race.

In a recent suite this removed most of the intermittent failures and trimmed a few minutes off the run, from deleting sleeps that padded for the slowest case.

The rule I give my team is simple. Never sleep for time. Wait for a condition. If you cannot name the condition you are waiting for, you do not understand the step yet.

Response waits do couple your test to API paths, so a route refactor can break them. I take that trade. A test that breaks loudly when the contract changes is worth more than one that passes by luck.

#TestAutomation #Playwright #QualityEngineering #SDET #FlakyTests

---

## Day 2 — 2026-06-17 — SDET engineering

**Why time.sleep() Is Killing Your Test Suite**

Most flaky test suites I have inherited share one root cause: someone reached for time.sleep() to make a test pass.

It works on their laptop. It works in the demo. Then CI runs on a loaded machine, the app takes 1.4 seconds instead of 0.8, and the test fails for reasons that have nothing to do with the product.

The fix is not a bigger sleep. A bigger sleep makes the suite slower and hides the race a little longer. Wait for the actual condition you care about.

Selenium has explicit waits. Playwright has web-first assertions and auto-waiting built in. Use them.

Before (Selenium):

    driver.find_element(By.ID, "submit").click()
    time.sleep(3)
    assert "Order placed" in driver.page_source

After:

    driver.find_element(By.ID, "submit").click()
    WebDriverWait(driver, 10).until(
        EC.text_to_be_present_in_element(
            (By.CSS_SELECTOR, ".status"), "Order placed"
        )
    )

The second version returns the moment the text appears, often in well under a second, and only fails if the condition never happens within the timeout. Faster and more honest.

A few habits that have worked for me:

- Wait on a specific element or state, never on the clock.
- Set one sane global timeout and stop sprinkling magic numbers.
- When a test is flaky, treat it as a real bug and read the trace before you retry it.
- Quarantine, do not delete. A test you mute and forget is worse than no test.

Retries have a place. They are a safety net, not a design. If your green build depends on the third attempt, you are shipping the race to production and not looking at it.

Sleeps feel like progress because the bar turns green. They are debt with interest, and CI collects.

#SDET #TestAutomation #QAEngineering #FlakyTests #Playwright

---

## Day 3 — 2026-06-18 — QA automation strategy

**Playwright vs Cypress: pick by your app boundary**

I have shipped suites in both Playwright and Cypress, and the choice usually comes down to one question: how much of your testing crosses a real browser boundary?

Cypress runs inside the browser, in the same event loop as your app. The debugging experience is hard to beat. You get time-travel snapshots, the test reruns on save, and on failure you see the exact DOM state. For a single-page app with one origin, my team gets green suites fast.

The boundary is where it bites. Cypress historically struggled with multiple tabs, origins, and native browser events. cy.origin helped, but I have still spent afternoons working around an OAuth redirect or an iframe on another domain.

Playwright runs out of process and drives the browser over the DevTools protocol. That is why it handles things Cypress finds awkward:

- multiple tabs and origins in one test
- real parallelism across workers on one machine
- Chromium, Firefox, and WebKit from the same script
- auto-waiting on actionability instead of arbitrary sleeps

A login I reuse everywhere looks like this in Playwright:

  const ctx = await browser.newContext({ storageState: 'auth.json' });
  const page = await ctx.newPage();
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();

Saving storageState once and loading it per worker cut our auth overhead, since most tests skip the UI login.

So my rule. Cypress when the app is one origin and the team values the inner-loop feel. Playwright when you have cross-origin flows, multiple engines, or you want parallelism without a dashboard. Pick the one whose constraints match your app, not the one with the louder launch.

#QAAutomation #Playwright #Cypress #SDET #TestAutomation

---

## Day 4 — 2026-06-19 — Web scraping & data extraction

**The Scraper That Broke Without Throwing an Error**

The scraper that ran fine for eight months broke on a Tuesday, silently. No exceptions, no stack trace. It started writing rows where about 40 percent of the price fields were empty, and nobody noticed until a downstream report looked wrong three days later.

The site had not blocked us. They had moved one product attribute out of the server-rendered HTML and into a JSON blob loaded by a later XHR call. Our Scrapy spider still got HTTP 200, still found the product container, still matched most selectors. It just missed the field that now arrived separately.

A scraper that returns data is not a scraper that returns correct data, and I had been treating them as the same.

What I do now on every project:

- Validate the shape, not only the response. I run records through Great Expectations (or a plain pydantic model) before they touch storage. Required fields, value ranges, sane row counts.

- Alert on absence. If a field that is normally 98 percent populated drops below 90, the run fails loudly. Silent nulls cost me more than any 403 ever has.

- Check the network tab first. Before I write a selector, I open the page in Playwright and watch what loads. Often the clean data sits in a JSON API the page calls anyway.

- Pin a golden sample. I save a few HTML fixtures and assert my parser against them in CI with pytest. When the site changes, a test breaks instead of a dashboard.

The hard part was never the requests. It is knowing the moment the page changed underneath you. A 403 tells you immediately. A moved field tells you nothing, and the silence is what hurts.

I would rather have a scraper that crashes on bad data than one that quietly fills my warehouse with holes.

#WebScraping #DataExtraction #Scrapy #Playwright #DataQuality

---

## Day 5 — 2026-06-20 — Using AI for QA Ops

**Stop Generating Tests With AI. Triage Them Instead.**

Stop asking an LLM to generate your whole Playwright suite. Start using it to triage the failures you already have.

I tried the "write all my tests with AI" thing last year. The model produced 40 specs in an afternoon. Most looked plausible. About a third asserted on the wrong thing, a handful tested behavior the app did not have, and almost all of them used brittle selectors like text=Submit that broke the next sprint. Reviewing that pile took longer than writing the tests by hand. The generation was fast. The trust was not.

So I moved the AI to the other end of the pipeline.

Now in CI, when a Playwright run goes red, a small script collects the failing test name, the error, the last few network requests, and the trace, then asks Claude one question. Is this a real regression, a flaky timing issue, or a stale selector? It does not fix anything. It posts a one-line guess into the GitHub Actions summary and tags the likely owner.

That is the part where AI actually earns its place. Classification, not authorship.

A rough split of where it helps:

- Failure triage: group 200 red runs into a few probable causes
- Flake detection: spot the same test failing only on retry, then flag it
- Selector drift: notice when locators stop matching after a UI change

The judgment still lives with me. I read the trace before I believe the label. But sorting signal from noise across a noisy suite is exactly the boring work I was bad at staying consistent on, and the model is steady there in a way I am not at 5pm on a Friday.

Generated tests feel productive. Triaged failures actually move the suite forward. If you only have budget for one AI experiment in QA this quarter, point it at your flake list, not your blank test files.

#QAAutomation #SDET #Playwright #AIinTesting #TestOps

---

## Day 6 — 2026-06-21 — AI-driven development

**Measuring AI Coding Tools Without Fooling Yourself**

Most teams measuring AI coding tools count the wrong thing. They track lines accepted, or how many people "use Copilot weekly." That tells you adoption, not value. I care about whether the code that ships is good, and whether it costs less to get there.

Here is what I actually measure on my teams.

Change failure rate, split by origin. We tag PRs that were mostly AI-generated and compare their rollback and hotfix rate against human-written ones. If the AI bucket fails more often in production, the speed is fake. We are just moving the cost downstream to on-call.

Review time per PR. AI makes it cheap to produce a 600-line diff. Someone still has to read it. If author time drops but reviewer time climbs, you have shifted work, not removed it. Track both sides.

Test signal, not test count. An AI will happily generate 40 pytest cases that all assert the function returns something. I look at mutation score (mutmut, Stryker) on AI-written tests, and whether they catch a deliberately seeded bug. A suite that goes green no matter what you break is worse than no suite.

Escaped defects per feature. This is the number that survives the noise. Pull it from your bug tracker, attribute it to the change, and watch the trend over a quarter.

A rough before/after I find believable:

  author time per PR: 4h -> 2h
  reviewer time per PR: 30m -> 50m
  change failure rate: flat or slightly up

That last line is the one to fix before you scale the rollout.

The honest trade-off is that good measurement is annoying. Tagging PRs and running mutation tests in CI costs you something. But if you cannot tell whether the tool is helping, you are paying for a feeling instead of a measured gain.

#AIDrivenDevelopment #SoftwareTesting #EngineeringMetrics #QualityEngineering #DevProductivity

---

## Day 7 — 2026-06-22 — CI/CD & test infrastructure

**Flaky Tests Are a Budget Line Now**

In 2026 the loudest CI/CD trend on my teams is not a new tool. Teams are finally treating flaky tests as a budget line instead of a vibe.

For years we tracked pass rate and called it a day. A pipeline at 95 percent green felt fine. Then someone measured our retries, and we found that maybe 1 in 12 failures was a real defect. The rest were timing races, shared state, and a Playwright locator that resolved before the network settled. We were paying for compute to rerun lies.

What changed this year is that the data finally lives where engineers look. We write every test result, with duration and retry count, to a small store and query it in CI.

  flaky_score = reruns_that_flipped / total_runs

Anything above a threshold gets quarantined automatically, not deleted. A quarantined test still runs and still reports, but it cannot block a merge. The owner gets a ticket. That one rule did more for trust in the suite than any framework upgrade.

The trade-off is real. Quarantine becomes a graveyard if nobody reads the tickets, so we cap it. If quarantine holds more than 2 percent of tests, the build warns and someone has to clean house.

The other shift is moving assertions earlier. Contract tests with Pact catch a broken API shape in seconds, before a 9 minute end-to-end run ever spins up a browser. We run k6 smoke checks on every PR, not just before release.

None of this is exotic. pytest gives you durations and JUnit XML for free. GitHub Actions can fail a job on a flaky-rate gate. The skill in 2026 is measuring the tests you already have and being honest about which ones deserve to block a deploy.

How does your team decide a test has earned the right to fail the build?

#TestAutomation #CICD #SDET #QAEngineering #FlakyTests

---

## Day 8 — 2026-06-23 — API & contract testing

**A Contract Testing Checklist I Actually Run**

Most "API tests" I inherit are really integration tests in disguise. They hit a live service, pass when the network is calm, and tell you nothing about whether the contract between two teams still holds. Last quarter a provider renamed a field from user_id to userId in a minor release. Every test stayed green. Three consumers broke in production.

Here is the checklist I now run for any API I own or depend on.

1. Write the schema down first. Capture request and response shape in OpenAPI or JSON Schema before you write the test. If you cannot describe it, you do not understand it yet.

2. Validate against that schema in every test. In pytest with the requests library, assert the status code, then validate the body with jsonschema. A 200 with the wrong shape is still a failure.

3. Separate fast from slow. Schema and contract checks run on every commit in GitHub Actions. Full end to end against a deployed environment runs nightly, not on every push.

4. Add consumer-driven contracts where teams hand off. Pact lets the consumer publish what it actually reads. The provider verifies against that, so a renamed field fails the provider build instead of production.

5. Test the unhappy path on purpose. 400, 401, 404, 422, and a malformed body. Most outages I have debugged were a 500 where someone expected a clean 4xx.

Two of these have caught more real bugs than any UI suite I have written: schema validation on every response, and consumer-driven contracts at team boundaries. Start there. The rest can wait a sprint.

What does your team verify, the response code or the actual shape?

#APITesting #ContractTesting #TestAutomation #QAEngineering #Pact

---

## Day 9 — 2026-06-24 — Test Automation

**The Flaky Test Was a Real Race Condition**

A test failed on CI about one run in twenty. Passed locally every single time. The kind of failure people retry until it goes green and forget about.

I stopped retrying and started logging. A retry that passes is not a fix, it is a deferral.

The test signed up a user, then asserted the welcome email landed in a fake inbox. Most runs the email was there. Sometimes it was not. Same code, same data.

The bug was a race. The signup endpoint returned 201 before the email job was enqueued, and the email went out a few milliseconds later. My laptop was slow enough that the assert always lost the race. CI was faster, so sometimes the assert ran first and saw an empty inbox.

The tempting "fix" is a sleep:

    time.sleep(2)
    assert inbox.count() == 1

That hides the race behind a magic number, slows the suite for everyone, and still flakes the day CI gets busy.

What I did instead was poll for the real condition with a bound:

    def wait_for(predicate, timeout=5, interval=0.05):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return True
            time.sleep(interval)
        return False

    assert wait_for(lambda: inbox.count() == 1)

Same idea as Playwright auto-waiting. You wait for the state you care about, not for a clock.

Two things helped me find it faster:
- Run the test in a loop with pytest-repeat until it fails, instead of hoping CI reproduces it.
- Log timestamps on the request and the side effect. The gap was obvious once I could see it.

Flaky tests usually tell you something true about timing or shared state. This one was a real bug a user could hit during a traffic spike.

#TestAutomation #FlakyTests #SDET #QualityEngineering #Pytest

---

## Day 10 — 2026-06-25 — SDET engineering

**Scaling a test suite without losing speed**

Our end-to-end suite went from 40 tests that ran in 4 minutes to about 1,800 that run in under 10. The hard part was never writing more tests. It was keeping them fast and trustworthy as the count grew.

A few changes did most of the work.

We killed the shared test database first. Every test that mutated global state was a landmine once we turned on parallelism. We moved to a fixture that spins up an isolated schema per worker (pytest-xdist with a per-worker Postgres schema), and the same tests that flaked at 8 workers passed at 32.

Then we stopped using sleeps. A grep for time.sleep in the repo returned more results than I want to admit. In Playwright we replaced them with web-first assertions:

    # before
    click("#save")
    time.sleep(2)
    assert visible("#toast")

    # after
    page.click("#save")
    expect(page.locator("#toast")).to_be_visible()

The second version waits only as long as it needs to, and it fails fast with a real reason.

Last, we split the suite by purpose instead of by folder. A small set of API-level tests (requests plus a few Pact contracts) covers most of the logic. The browser tests cover the handful of flows a user actually walks through. That ratio is what keeps wall-clock time down, because UI tests are the expensive ones.

The trade-off is honest. Per-worker isolation costs setup time, and you pay for more CI runners. We decided a 10-minute signal that engineers trust beats a 4-minute signal they learned to ignore.

If your suite is getting slower than your features, look at state and sleeps before you blame the test count.

#SDET #TestAutomation #Playwright #CICD #QualityEngineering

---

## Day 11 — 2026-06-26 — QA automation strategy

**Stop Waiting On The Clock In Your E2E Tests**

Most flaky Playwright and Cypress tests I see are not flaky because of the browser. They are flaky because the test waits on a clock instead of a condition.

I went through our suite last quarter and the pattern was almost always the same. Someone hit a timing bug, dropped in a sleep, the test went green, and it sat in the codebase for a year. Then it failed once a week in CI for no obvious reason, and everyone learned to just re-run the job.

Here is the shape of the problem in Playwright:

  await page.click("#submit")
  await page.waitForTimeout(2000)
  expect(await page.isVisible("#result")).toBe(true)

That 2000 is a guess. On a fast machine it wastes two seconds. On a loaded CI runner it is sometimes not enough, and the test fails even though the app is fine.

Wait for the thing you actually care about instead:

  await page.click("#submit")
  await expect(page.locator("#result")).toBeVisible()

Now the test waits up to the timeout but returns the moment the element shows up. Faster on average, and it stops failing under load.

The rule I push on every team is simple. Treat waitForTimeout (and Cypress cy.wait with a number) as a code smell that has to be justified in review. If you genuinely need to wait, wait on a network response, a DOM state, or a polled assertion, never a raw duration.

A few things we agreed on:
- No bare numeric waits in merged tests.
- One retry on the whole job, not per-test. Per-test retries hide real bugs.
- A test that needs three reruns to pass gets quarantined, not ignored.

We did this one folder at a time, and our CI failures from timing dropped to almost nothing. The tests also got a little faster, which was a nice surprise.

If your team re-runs CI as a habit, grep for the sleeps first. That is usually where the noise lives.

#QAAutomation #TestAutomation #Playwright #FlakyTests #SDET

---

## Day 12 — 2026-06-27 — Web scraping & data extraction

**Your Scraper Is Racing the Page**

The pitfall that burned me most in web scraping was trusting that an element being present in the DOM meant it was ready to read.

I had a Playwright job pulling product prices off a few hundred pages a night. It passed in dev, passed in CI, then started writing rows where the price was null or, worse, the old cached value from a skeleton state. No exception. No failed status. Just quietly wrong data into a report that someone downstream actually used.

The cause was a race. The page rendered a placeholder, my selector matched it, I grabbed text, and the real value arrived 200ms later via an XHR call. wait_for_selector returned the instant the node existed, which is not the same as the node holding the value I wanted.

Two fixes mattered. First, stop waiting on presence and start waiting on the thing you actually care about. With Playwright I waited on the network response instead of the element:

  page.wait_for_response(lambda r: "api/price" in r.url and r.status == 200)

Or I asserted on content rather than existence:

  expect(locator).not_to_have_text("--")

Second, treat scraping output like test output. I added a Great Expectations check on the extracted table: price is non-null, numeric, and inside a sane range. If 5 percent of rows fail, the run fails loudly instead of shipping garbage.

The mindset is the real lesson. A scraper is a test that asserts on someone else's UI. If you would not let a flaky locator pass in your e2e suite, do not let it pass in your data pipeline either. The stakes are higher, because nobody reads scraper output as carefully as a red build.

When in doubt, scrape the same page twice and diff. If the runs disagree, your selector is racing.

#WebScraping #DataEngineering #Playwright #TestAutomation #DataQuality

---

## Day 13 — 2026-06-28 — Using AI for QA Ops

**Selenium vs Playwright for AI QA Ops**

Last quarter I migrated part of our suite from Selenium to Playwright while wiring AI-assisted test maintenance into both. Here is what actually mattered.

The AI angle first, because that is the hype. Both tools now claim "self-healing" locators and LLM-generated tests. The thing nobody tells you: AI is only as good as the snapshot it gets to read. Playwright hands an AI agent a clean accessibility tree, so when I ask a model to fix a broken selector it sees roles and labels and proposes getByRole("button", { name: "Submit" }). With Selenium I had to build that context myself, scraping the DOM first.

Where Selenium still wins: real browser coverage and legacy stacks. Need actual Safari on a device farm, or stuck with ten years of Java page objects? Ripping that out for an AI demo is a bad trade.

Where Playwright helps for AI ops:
- auto-waiting kills most flake, so the AI debugs logic, not timing
- trace viewer gives a model a structured failure to read, not a raw stack trace
- one API across Chromium, Firefox, WebKit

A concrete before/after from our flaky login test.

  Before (Selenium, explicit wait, still flaked):
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "submit")))

  After (Playwright, auto-wait):
    page.get_by_role("button", name="Log in").click()

I run both behind one pytest harness reporting into GitHub Actions, so the maintenance script does not care which engine ran. My honest take: use AI to triage failures and draft locators, not to author whole suites. The model is a fast junior that needs structured output to stop guessing.

Has anyone gotten AI selector healing stable on Selenium without heavy plumbing?

#QAAutomation #Playwright #Selenium #SDET #TestAutomation

---

## Day 14 — 2026-06-29 — AI-driven development

**When AI Writes Tests That Cannot Fail**

Last quarter I let an AI agent generate an entire integration test suite for a payments service. About 240 tests, all green, written in roughly two days of prompting. I was happy. Then we shipped a bug to staging that the suite should have caught, and I went looking for why.

The tests were green because most of them asserted almost nothing.

A typical generated case called the endpoint, checked that the response status was 200, and moved on. No assertion on the response body, no check that the refund amount matched, no verification that the ledger row was written. The model learned the shape of a pytest test without the intent of one. It optimized for "passes" because that is what looked correct in my prompt.

What I do now on AI-assisted test work.

- I mutate the code on purpose. I break the refund math, flip a boolean, or drop a field, then run the suite. If nothing goes red, the tests are decoration. This is manual mutation testing, and mutmut or cosmic-ray can automate part of it.
- I review assertions first and setup second. Generated setup is usually fine. The assertions are where the model gets lazy.
- I ask for one test, read it carefully, then ask for more in that style. Reviewing 240 tests at once means reviewing none of them.

I still use the agent every week. It is fast at boilerplate, fixtures, parametrize tables, and turning a curl command into a requests call. But a passing test is a claim, and AI is very good at producing claims that have nothing behind them.

The lesson I keep relearning is that generated coverage is not tested behavior. A suite that cannot fail is worse than no suite, because it tells you that you are safe when you are not.

#TestAutomation #AIAssistedDevelopment #SDET #QualityEngineering #MutationTesting

---

## Day 15 — 2026-06-30 — CI/CD & test infrastructure

**Stop Quarantining Flaky Tests**

Stop quarantining flaky tests. Delete them or fix them this week.

The quarantine folder is where coverage goes to die. I have seen it on three teams. A test goes flaky, someone tags it @skip or moves it into a "known-flaky" suite with a ticket, and CI goes green again. Everyone moves on. Six months later that folder holds 80 tests and nobody trusts one of them. The original failure is still there. You just stopped looking at it.

The honest version is harder but cheaper over time. When a test flakes, do one of two things, today.

Fix the root cause. Most flake is a race, a hardcoded sleep, or an order dependency. In Playwright, swap the sleep for a web-first assertion like expect(locator).toBeVisible(). In pytest, kill shared state with proper fixtures and stop relying on test order.

Delete it. If a test is not worth fixing, it is not worth keeping. A skipped test is worse than no test, because it shows up in the count and lies about coverage.

What I do instead of a quarantine bucket: run the suite with a small retry budget so one transient failure does not block a deploy, but log every retry. Then I read the retry log weekly. A test that needed a retry twice in a week is a bug report, not a footnote.

One number to watch. If more than about 1 to 2 percent of your runs need a retry, the tests are not your problem. It is the environment, the test data, or timing assumptions baked into the app. Flaky tests are usually telling you the truth about production. Listen before you mute them.

The quarantine folder feels like progress because the build is green. Green is not the goal. Trust is.

#TestAutomation #CICD #QAEngineering #FlakyTests #SDET

---

## Day 16 — 2026-07-01 — API & contract testing

**The contract testing metric most teams ignore**

Most teams I have worked with track how many contract tests they have. Almost none track the only number that matters: how many production incidents those tests would have caught before deploy.

We started measuring that last year. The setup was Pact for consumer-driven contracts between our services, plus Postman/Newman in CI for the public API. Counting tests told us nothing useful, so we changed what we logged.

Here is what we measure now.

- Escaped contract breaks. Every time a service ships a breaking change (renamed field, type swap, removed enum value) that reaches staging or prod, we tag it. The goal is to drive this toward zero. It is the closest thing to a true defect-escape rate for integrations.

- Time-to-detect. With Pact verification running on every provider build, a breaking change fails the provider's pipeline in minutes instead of surfacing as a 500 in a downstream team's service two days later. We went from "found by a partner team" to "found by the provider's own CI."

- Mean time to diagnose. A good contract failure names the consumer, the interaction, and the exact field. Compare that to reading a stack trace from an integration test that only says the response did not match.

The payoff is not the test count. It is the cross-team debugging hours you stop spending.

One honest trade-off. Contract tests verify shape and agreed behavior, not real load or data correctness. They will happily pass while the provider returns the wrong value in the right schema. So I pair them with a small set of end-to-end checks and k6 for load, and I keep the contract suite narrow on purpose.

If you can only add one metric this quarter, log escaped contract breaks. It changes the question from "are we writing enough tests" to "are the right changes failing fast."

#ContractTesting #APITesting #QAEngineering #TestAutomation #Pact

---

## Day 17 — 2026-07-02 — Test Automation

**Self-Healing Tests Are Here, Judgment Is Not**

In 2026 I stopped writing most of my UI selectors by hand, and my flaky test rate dropped more than any framework upgrade ever gave me.

The trend everyone talks about is AI generating whole test suites. The part that actually changed my day to day is smaller and less exciting: self-healing locators and AI-assisted triage sitting on top of tools I already use.

Here is what I mean in practice. With Playwright I lean on role and label based locators, and when the DOM shifts the runner can suggest a repaired selector instead of just going red.

Before:
  page.locator("#submit-btn-3a9f")
After:
  page.get_by_role("button", name="Place order")

The first one breaks on every redeploy. The second survives most refactors, and when it does break, the AI suggestion is usually close enough to review in seconds.

I am careful about where I let this run. A suggested locator fix is a pull request I read, not a silent auto-merge. The moment a tool rewrites assertions on its own, you lose the one thing tests are for, catching the change you did not intend.

What I have found useful so far:
- Let AI propose locator repairs, but gate them behind code review.
- Use it to cluster failures in CI (GitHub Actions logs are noisy), so I triage one root cause instead of forty red checks.
- Keep generated tests in a quarantine suite until a human has read them.

The skill that matters in 2026 is not prompting. It is knowing which failures are real, which fixes are safe to accept, and where a confident suggestion is quietly wrong. The tooling got faster. The judgment is still ours.

#TestAutomation #SDET #Playwright #QAEngineering #AITesting

---

## Day 18 — 2026-07-03 — SDET engineering

**The 7-Step Checklist I Run Before Merging Any Test**

Most flaky test suites I inherit are not flaky because of bad luck. They are flaky because nobody ran a checklist before merging the test. Here is the one I run on every new UI or API test before it goes into main. It takes ten minutes and saves hours later.

1. Kill the hard waits. Search the diff for sleep(), time.sleep, and waitForTimeout. Replace each with a condition. In Playwright, expect(locator).toBeVisible() already retries. In Selenium, use WebDriverWait with an expected condition. A fixed sleep is a bet on the slowest machine you have never seen.

2. Pin the selector to something stable. Prefer data-testid over a CSS nth-child, and either over an XPath that walks the DOM. If the test breaks when a designer moves a div, the selector was wrong.

3. Run it three times in a row locally. Same machine, back to back. If it fails once out of three, it is already flaky. Fix it now, not after it poisons the dashboard.

4. Run it isolated, then in the full suite. Order-dependent tests pass alone and fail together. Shared state, leftover DB rows, a session that bled over. Find it before CI does.

5. Check the teardown. Every record the test creates, it should remove. I have seen suites slow to a crawl because nobody cleaned up.

6. Make the failure message say what broke. assert resp.status == 200 tells you nothing. assert resp.status == 200, resp.text gives you the body when it is a 500.

7. Tag it. smoke, regression, slow. Future you will want to run a subset in a hurry.

I do not always get all seven right. But the suites where I skipped this are the ones I am still apologizing for. Boring checklists keep CI green at 2am.

What is on your pre-merge list for a new test?

#SDET #TestAutomation #QAEngineering #Playwright #FlakyTests

---

## Day 19 — 2026-07-04 — QA automation strategy

**The flaky test was right, my assertion was wrong**

Last month a single Playwright test failed about one run in twenty. Always the same assertion, never on my machine, only in CI. The kind of failure that tempts you to add a retry and move on.

I did not add the retry. I added logging instead.

The test filled a form, clicked Save, then asserted a success toast was visible. On the failing runs the click landed, the network request fired, but the assertion timed out. My first guess was the usual one: the element was not ready. Wrong. The toast had already appeared and disappeared before Playwright looked for it.

The real cause was a race between two things I did not control together. The app showed the toast for 3 seconds. In CI, under load, the runner sometimes paused long enough between the click and the assertion that the toast was gone by the time we checked.

The fix was not a longer timeout. A longer timeout would have made it worse, because the toast was already gone. I changed what we waited on:

  // brittle
  await page.click('text=Save')
  await expect(page.locator('.toast')).toBeVisible()

  // deterministic
  const resp = page.waitForResponse('**/api/save')
  await page.click('text=Save')
  await (await resp).finished()
  await expect(page.locator('[data-saved="true"]')).toBeVisible()

I tied the assertion to a state that persists (a data attribute the app sets after save) instead of a transient animation.

What I take from this now: flaky usually means I am asserting on something with a lifetime shorter than my own scheduling jitter. The retry hides that. The state model fixes it.

I run suspected flaky tests 50 times in a loop before I trust a fix. One green run proves nothing.

#QAautomation #TestAutomation #Playwright #FlakyTests #SDET

---

## Day 20 — 2026-07-05 — Web scraping & data extraction

**Scaling a Scraping Suite Without Killing Speed**

Our scraping suite went from 40 spiders to over 300, and the thing that nearly killed us was not a website change. It was the suite itself. A full run took close to two hours, most of it spent waiting on network I/O while a single process sat idle.

The first instinct was to throw more retries and longer sleeps at flaky sites. That made everything slower and hid real failures. So we reworked it.

What actually changed the numbers:

- Concurrency where it belongs. We moved the bulk of fetches to async httpx with a bounded semaphore (start around 20, tune per host). Scrapy already does this well, so there we just raised CONCURRENT_REQUESTS_PER_DOMAIN instead of fighting the framework.

- Separate the parse from the fetch. Parsing HTML with selectolax or parsel is CPU work and does not belong in the same coroutine as the download. We cache raw responses to disk, so when a selector breaks we re-parse from cache instead of re-hitting the site. That cut our debug loop from minutes to seconds.

- Test selectors against fixtures, not the live web. We snapshot a few real pages per source and run pytest over them. A live smoke test runs nightly in GitHub Actions, but the fast suite never touches the network. Live tests that gate every commit are how you get a red pipeline because a marketing banner moved.

- Rate limit per host and honor robots. That kept us off block lists.

The trade-off is real. More concurrency means more partial failures to reason about, and cached fixtures drift from production. We accept that. A two-hour suite nobody runs is worse than a ten-minute suite with a nightly live check behind it.

What I optimize now is the feedback loop, not raw crawl speed.

#WebScraping #TestAutomation #Python #Scrapy #DataEngineering

---

## Day 21 — 2026-07-06 — Using AI for QA Ops

**I Let an LLM Triage Our Flaky Tests**

I let an LLM triage our flaky test failures last quarter, and the first version made things worse. It would "explain" a failure with confident nonsense and we chased ghosts. The fix was to stop asking it to reason in the abstract and start feeding it structured evidence.

When a Playwright test fails in GitHub Actions, we already capture the trace, the failing assertion, and the last few network requests. Instead of pasting a stack trace into a prompt, we hand the model a compact JSON record and ask one narrow question: is this a product bug, a test bug, or infra.

    payload = {
        "test": test_id,
        "error": err.splitlines()[0],
        "selector": failed_selector,
        "status_codes": recent_status_codes,
        "retries_passed": retried_ok,
    }

The prompt is boring on purpose. Classify as product_bug, test_bug, or infra. Return JSON with category, confidence, and why. If status_codes contain 5xx, prefer infra. If retries_passed is true, prefer test_bug.

Two things made this useful. We gate on confidence: anything under 0.7 goes to a human, no auto-labeling. And we never let the model close or mute a test. It writes a suggested label on the GitHub issue. A person still pulls the trigger.

On a typical week it sorts 60 to 70 percent of failures correctly, enough to halve the morning queue. The wins are the obvious 5xx and timeout failures that humans should never have looked at, not the clever cases.

The trap is treating the model as an oracle. It is a fast first-pass sorter that works only when you give it the same evidence you would give a junior engineer. Garbage context in, confident garbage out. I would not let it touch test selection yet.

#QAAutomation #SDET #TestEngineering #AIOps #Playwright

---

## Day 22 — 2026-07-07 — AI-driven development

**AI Writes Tests That Pass And Prove Nothing**

Last month an AI coding assistant wrote 40 tests for a new checkout flow in about ten minutes. All green. I almost shipped it. Then I read them.

Every assertion was checking that the mock returned what the mock was told to return. The tests confirmed nothing about the real code. This is the trap I keep hitting with AI-generated tests. They pass, the coverage number climbs, and the suite proves almost nothing.

The model is good at producing tests that look right. It mocks the payment client, stubs the database, then asserts the stub was called. Green checkmark, zero signal. When I deleted the real function body and replaced it with return None, 38 of those 40 tests still passed.

That last part is the check I now run on any generated test. Break the code on purpose, then run the suite. If tests still pass, they were testing the mocks. If an assertion only repeats the arrange step, delete it. If a test has no clear failure mode, it has no reason to exist.

I still let the assistant draft tests. It is fast at the boring scaffolding, the fixtures, the parametrize tables. But I write the assertions myself, or rewrite them to check observable behavior: the HTTP status, the row in the database, the email that got queued. With pytest I lean on real objects and a test database far more than mocks now.

A coverage number an AI hands you is a starting question, not an answer. Run mutmut or cosmic-ray once in a while and watch how much covered code survives mutation. The gap is usually wider than the dashboard suggests.

Generated tests are a draft. Treat them like one.

#TestAutomation #AIDrivenDevelopment #SDET #Pytest #SoftwareTesting

---

## Day 23 — 2026-07-08 — CI/CD & test infrastructure

**Hosted vs Self-Hosted CI Runners for Test Suites**

I have run end-to-end suites on both GitHub Actions hosted runners and a self-hosted runner fleet. After two years of paying for both, here is where I land.

Hosted runners win on day one. Zero maintenance, every job starts on a clean VM, and you stop worrying about state leaking between runs. For a Playwright suite that spins up a browser, hits a staging API, and tears down, that clean slate is worth a lot. Flaky tests are hard enough without a poisoned cache from last Tuesday.

The pain shows up at scale. Our browser tests pull a few hundred MB of node_modules plus the Playwright browser binaries on every job. On a cold hosted runner that is two to three minutes of setup before a test runs. Multiply by 40 shards and the bill (and the wall-clock time) gets ugly fast.

Self-hosted fixes the cold start. We bake the dependencies and browsers into the runner image, so a job starts testing in seconds. We also get bigger machines for k6 load runs that would choke a standard hosted runner. The trade-off is real. Now you own patching, autoscaling, and the security story for anything that touches your network.

Where I have settled: hosted runners for PR checks, where isolation matters more than speed and the volume is spiky. Self-hosted for nightly full-suite and load tests, where warm caches and big machines pay off.

One thing that bit us: self-hosted runners reuse the filesystem by default. A leftover .env or a running Docker container from a previous job will make tests pass that should fail. We now wipe the workspace and prune containers in a pre-job step.

If you are starting out, use hosted runners and measure. Move the slow jobs off once the numbers justify the cost.

#CICD #TestAutomation #SDET #GitHubActions #Playwright

---

## Day 24 — 2026-07-09 — API & contract testing

**The Contract Test That Saved a Release**

A backend team renamed a JSON field from "userId" to "user_id" and shipped it. Our mobile app stopped showing order history for two days before anyone noticed. The API tests were all green. That was the moment I stopped trusting status codes alone.

Here is what bit us. We had a suite in Postman and Newman hitting the provider, asserting 200s and a few field values against a recorded example. The provider changed its response shape. Our tests still passed, because they ran against a stub nobody had updated in weeks. The real consumer broke in production.

We fixed it with consumer-driven contract testing using Pact. The consumer (the mobile client) declares what it needs from a response, and that expectation becomes a contract. The provider verifies against it in its own pipeline. If the provider drops or renames a field the consumer reads, the build goes red instead of the consumer in production.

A consumer expectation looked roughly like this:

  .willRespondWith({
    status: 200,
    body: { user_id: like("u-123"),
            items: eachLike({ sku: like("ABC") }) }
  })

The part that mattered was not the tool. It was moving the check left. Before, a shape mismatch surfaced in staging during manual testing. After, it surfaced on the provider's pull request in GitHub Actions, with the consumer named in the failure.

Two honest trade-offs. Pact adds friction, because someone has to own the broker and versioning, and teams that do not talk to each other will hate it at first. It does not test behavior, only the contract. We kept k6 for load and a few end to end checks for flows that move money.

Contract tests catch the cheap, stupid breakages early. That is most of them.

#ContractTesting #ApiTesting #Pact #QualityEngineering #TestAutomation

---

## Day 25 — 2026-07-10 — Test Automation

**Stop Asserting Business Logic In The Browser**

Stop writing every UI test as an end-to-end test. Push the assertion down to the lowest layer that can still catch the bug.

I spent years maintaining Selenium suites where logging in, creating an order, and checking a tax calculation all ran through the browser. The tax math was correct in code. The test failed anyway because a modal animation shifted a button by 4 pixels. We were paying full E2E cost to verify pure business logic.

Here is the shift that helped my team:

- A wrong tax total is a unit test against the calculator.
- A broken /orders contract is an API test with requests or Postman/Newman.
- A field that does not save is an integration test against a real database.
- "Can a user actually check out" is the E2E test, and we keep a handful of those in Playwright.

The browser is the most expensive and least stable place to assert anything. So I only assert there when the thing under test is the browser itself: rendering, routing, and the wiring between real services.

A before/after from one flow:

  before:
    Selenium test logs in, navigates, submits, reads total from a <span>
  after:
    pytest test calls calculate_total() directly with 12 cases
    one Playwright test confirms the number reaches the screen

The before was 40 seconds and flaked maybe one run in ten. The after is milliseconds for the math, plus one slow check that rarely lies to me.

This is not anti-E2E. E2E catches integration bugs nothing else will. But when a test fails, I want it to point at the broken thing, not at a layer it happened to pass through. A failing unit test names the function. A failing E2E test names your afternoon.

Write the test at the layer that owns the risk.

#TestAutomation #QA #SDET #Playwright #TestStrategy

---

## Day 26 — 2026-07-11 — SDET engineering

**The QA Metrics That Actually Prove ROI**

Most QA dashboards I inherit measure the wrong thing. They count tests. Test count tells you little about whether the suite pays for itself. Here is what I track instead.

Escaped defects per release. Bugs that reached production divided by total bugs found that cycle. This is the only number that answers what leadership cares about: is testing catching things before customers do. When it climbs, the suite has blind spots that new test cases alone will not fix.

Mean time to detect, then mean time to a green pipeline. If a Playwright run takes 40 minutes and flakes twice a week, developers stop trusting it and start merging around it. I would rather have 200 reliable checks than 2000 that people ignore.

Flake rate per test. I tag every test that fails then passes on rerun with no code change. Anything above a few percent gets quarantined and fixed or deleted. A flaky test is a liability, not an asset.

Cost per bug caught. Rough, but useful. Take the engineering hours that went into a layer (unit, API with pytest and requests, end to end) and divide by the defects it caught last quarter. End to end almost always looks expensive, which is the point. It pushes work down the pyramid where it is cheaper.

The ROI argument that lands with managers is not "we have 95 percent coverage." Coverage is an input. They want outputs: fewer hotfixes, shorter releases, fewer 2am pages.

One caveat. Every metric becomes a target and then a lie. If I only reward escaped-defect numbers, people stop logging small bugs. So I read these together, monthly, and treat sudden improvement as a reason to look, not celebrate.

Measure what production costs you. Let that decide where the tests go.

#SDET #TestAutomation #QAEngineering #SoftwareTesting #EngineeringMetrics

---

## Day 27 — 2026-07-12 — QA automation strategy

**The Test Nobody Wrote On Purpose**

In 2026 the test I trust least is the one nobody wrote on purpose.

The pattern I keep seeing is teams generating end to end tests from an LLM looking at the running app. You point it at a flow, it produces a Playwright spec, and you have forty new tests by lunch. The coverage number goes up. The confidence does not.

Here is what I learned the hard way. Generated tests are good at describing what the app currently does and useless at describing what it should do. They lock in the bug. A model watching a checkout page will happily assert that the total is 0.00 if that is what rendered, because it has no idea what the price was supposed to be.

So my rule for the year is simple. Use generation for the boring scaffolding, write the assertions yourself.

In a Playwright suite that looks like this:

  // generated: fine
  await page.getByRole('button', { name: 'Place order' }).click()

  // mine: the part that actually catches regressions
  await expect(page.getByTestId('order-total')).toHaveText('$42.00')

Let the tool draft the locators, the navigation, and the form filling. The expected values and the boundary cases come from a human who knows the requirement. That is the thing a product person would argue about in a meeting.

Two habits have paid off. I review generated tests in the PR like any other code, and I reject anything where the assertion just mirrors current output. I also keep a small set of hand written contract tests with Pact for the service boundaries, because that is where generation helps least and breakage costs most.

AI is good at typing. It is bad at knowing what correct means. That gap is still the job.

#QAAutomation #SoftwareTesting #Playwright #SDET #TestStrategy

---

## Day 28 — 2026-07-13 — Web scraping & data extraction

**A Scraping Checklist That Survives Past Week Three**

Most scraping projects break in week three, not day one. Selectors drift, the site adds a captcha, and nobody notices until the data file is empty. Here is the checklist I run before writing extraction code.

1. Check the API first. Open DevTools, the Network tab, filter by Fetch/XHR, and reload. Half the time the page is already calling a clean JSON endpoint. Hitting that with requests beats parsing rendered HTML.

2. Read robots.txt and the terms. This is a legal and reputational call, not only a technical one. Know what you can pull, and at what rate, before you build.

3. Pick the lightest tool that works. If the data is in the HTML, use requests plus a parser. If it appears only after JavaScript runs, reach for Playwright. I move to a browser only with proof the content is client side.

4. Anchor selectors to stable attributes. Long CSS chains like div > div > span break on the next redesign. Prefer data-testid, an id, or an aria-label. Each selector is a maintenance liability.

5. Throttle and identify yourself. Add a delay between requests, set a real User-Agent, and respect 429 responses with backoff. One thread hammering a site gets you blocked.

6. Validate before you trust. I run rows through Great Expectations or a few pytest checks: column count, no nulls in key fields, types match. A scraper returning wrong data quietly is worse than one that crashes.

7. Cache raw responses. Save the raw HTML or JSON before parsing. When a selector breaks, you debug the saved page, not the live site.

8. Schedule with monitoring. A GitHub Actions cron run is fine. Make it scream when row count drops or a request fails.

Scraping is easy. Keeping it alive is the work.

#WebScraping #DataExtraction #Python #Playwright #TestAutomation

---

## Day 29 — 2026-07-14 — Using AI for QA Ops

**A flaky test usually caught a real race**

Last month I spent two days chasing a Playwright test that failed about 1 in 7 runs in CI and never once on my laptop. Classic non-determinism. The error was a timeout on a "Save" button click, which told me almost nothing.

Here is where I used AI well, and where I did not.

What worked: I gave the model the evidence, not the source. The Playwright trace zip, the failing run's console log, and three passing logs for contrast. I asked it to diff the timelines and tell me what was different in the failing case, not to "fix the flaky test." That framing matters. It found that the failing runs all had a network response for /api/profile arriving after the click, while passing runs had it arrive before. I had skimmed past that twice.

The bug was ours. The button was enabled optimistically, then briefly re-disabled while a background fetch resolved. My click landed in that window. The test was honest. The app had a race.

The fix was boring and correct:

    await expect(page.getByRole("button", { name: "Save" })).toBeEnabled();
    await page.getByRole("button", { name: "Save" }).click();

instead of clicking the moment the button appeared.

What did not work: when I asked the model to "make this test reliable," it suggested a hardcoded wait and a try/except retry. That hides the race and ships a real bug to users.

So my rule now. I use AI to read evidence faster than I can and form a hypothesis. I do not let it write the fix from a prompt that only describes the symptom. A retry that turns red to green is not a fix. It is a slower way to find out in production.

If a test is flaky, assume it caught something real until you have proof otherwise.

#QAAutomation #Playwright #FlakyTests #TestEngineering #AIforQA

---

## Day 30 — 2026-07-15 — AI-driven development

**AI Writes Tests Fast. That Is the Trap.**

When our Playwright suite was 40 tests, AI writing the tests felt like magic. At 1,200 tests it became the reason CI took 35 minutes and nobody trusted a red build.

The problem was not the AI. It was that I generated tests at scale the same way that worked when the suite was tiny. Each prompt produced a self-contained spec: log in, navigate, set up data through the UI, assert one thing, tear down. Forty of those run fine. Twelve hundred means twelve hundred logins and a flake rate that climbs every week.

What fixed it was changing what I asked the model to produce, not how much.

A few rules I now enforce:

- Seed state through an API or fixture, not the UI. The model writes the assertions, but data setup goes through a requests or Newman call or a pytest fixture. Browser steps are reserved for what needs a browser.
- Make it write the smallest test that fails for one reason. A spec with five assertions across three pages is three tests pretending to be one.
- Force shared setup. I give it the existing fixtures and page objects and reject anything that re-implements login.
- Tag and shard. New tests land tagged smoke or regression, so GitHub Actions runs smoke on every push and the full set on merge, parallel across workers.

The result was a suite that shards cleanly because the tests are independent and cheap.

Speed at scale is an architecture problem. AI makes it easy to write more tests, which is exactly why it buries you when the shape of those tests is wrong. I spend more time now on the prompt and the fixtures than on the test bodies, and the suite runs in about 6 minutes instead of 35.

The model is a fast junior who never gets bored. You still own the design.

#TestAutomation #SDET #Playwright #QualityEngineering #CICD

---

