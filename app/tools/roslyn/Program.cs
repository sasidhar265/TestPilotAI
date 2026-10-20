using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

// Parse supplied text only. Never load a generated project or execute generated code/MSBuild.
var options = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
var files = JsonSerializer.Deserialize<SourceFile[]>(Console.In.ReadToEnd(), options)
    ?? throw new InvalidDataException("Source files are required.");
var findings = new List<SyntaxFinding>();
foreach (var file in files)
{
    var tree = CSharpSyntaxTree.ParseText(file.Content,
        new CSharpParseOptions(LanguageVersion.CSharp12), path: file.Path);
    foreach (var diagnostic in tree.GetDiagnostics().Where(item => item.Severity == DiagnosticSeverity.Error))
    {
        var position = diagnostic.Location.GetLineSpan().StartLinePosition;
        findings.Add(new SyntaxFinding(file.Path, position.Line + 1, position.Character + 1,
            diagnostic.Id, diagnostic.GetMessage(System.Globalization.CultureInfo.InvariantCulture)));
        if (findings.Count >= 100) break;
    }
    if (findings.Count >= 100) break;
}
Console.Write(JsonSerializer.Serialize(findings, options));

record SourceFile(string Path, string Content);
record SyntaxFinding(string Path, int Line, int Column, string Code, string Message);
