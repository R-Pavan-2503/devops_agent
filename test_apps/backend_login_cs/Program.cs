var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
// Add mock service
builder.Services.AddSingleton<backend_login_cs.Services.IAuthService, backend_login_cs.Services.MockAuthService>();

var app = builder.Build();

app.UseAuthorization();
app.MapControllers();
app.Run();