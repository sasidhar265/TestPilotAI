# Create Jira stories from approved requirements

In the stories toolbar, enter the reviewer name and choose **Approve selected**.
**Continue to scenarios** is immediately beside approval and becomes available when all
stories are approved. Jira publication is optional and does not block scenario generation.

Keep the stories to publish selected, then choose **Upload to Jira**. The dialog creates
new issues; it does not modify existing issues or attach a file. Enter the project key
and the issue type name supported by that project (the initial value is `Story`).
Choose **Create Jira stories** to publish selected, approved stories only.

Configure `JIRA_BASE_URL`, `JIRA_EMAIL`, and `JIRA_API_TOKEN` on the application server.
The account must have permission to create issues in the chosen project. Each issue contains
the story title, narrative, source excerpt, acceptance criteria, source story ID, and
reviewer name. Creation follows the [Jira Cloud issue API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-post).
Projects requiring additional mandatory fields may reject this basic story payload.

The dialog returns issue links and preserves successful results if a later issue fails.
It stops at the first failed or unconfirmed result and does not automatically retry writes.
Created or unconfirmed stories cannot be resent in the current workspace session. Check
Jira before retrying after a reload; this session guard is not durable deduplication.
Editing a story requires renewed approval, but does not update its previously created Jira issue.

Local verification uses mocked Jira responses and ReqnRoll approval-boundary scenarios;
it does not establish successful creation in your Jira project.
