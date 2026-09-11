using System;
using System.IO;
using Reqnroll;

namespace Generated.StepDefinitions;

[Binding]
public sealed class Hooks
{
    [BeforeTestRun]
    public static void PrepareReports()
    {
        Directory.CreateDirectory(Path.Combine(AppContext.BaseDirectory, "TestResults", "Reports"));
    }
}
