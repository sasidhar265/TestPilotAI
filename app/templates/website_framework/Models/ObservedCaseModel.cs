namespace Website.Automation.Models;

public sealed record ObservedCaseModel(
    string Id, string Category, string PageId, string Kind, string Expected,
    string Title, string SelectorKey = "", string DestinationUrl = "",
    string DestinationTitle = "");
