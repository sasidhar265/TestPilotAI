using System.Text.Json;
namespace QualityLifecycle.Automation.Models;
public sealed record RoleAccessFixtureModel(
    string Role, string[] Targets, string AllowedPath, string AllowedMethod,
    JsonElement AllowedBody, int AllowedStatus, string DeniedPath, string DeniedMethod,
    JsonElement DeniedBody, int DeniedStatus, string ChangedRole, string HomePath);
