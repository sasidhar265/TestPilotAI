using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;

namespace Generated.StepDefinitions
{
    public sealed class ApiResponse
    {
        public int Status
        {
            get;
        }
        public string Body
        {
            get;
        }
        public IReadOnlyDictionary<string, string> Headers
        {
            get;
        }

        public ApiResponse(int status, string body, IReadOnlyDictionary<string, string> headers)
        {
            Status = status;
            Body = body;
            Headers = headers;
        }
    }

}
