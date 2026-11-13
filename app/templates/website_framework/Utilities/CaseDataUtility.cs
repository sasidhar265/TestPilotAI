using System.Text.Json;
using Website.Automation.Models;
namespace Website.Automation.Utilities;
public static class CaseDataUtility
{
    public static ObservedCaseModel Load(string id) =>
        JsonSerializer.Deserialize<List<ObservedCaseModel>>(
            File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Input", "CaseData.Json")),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!
            .Single(item => item.Id == id);
}
