// Generated on {generation_date} with {generator_name} {generator_version}
#pragma once

#ifdef MYLIB_EXPORTS
#define MYLIB_API __declspec(dllexport)
#else
#define MYLIB_API __declspec(dllimport)
#endif

#define EXPORT_IT(x) extern "C" __declspec(dllexport) void __cdecl x(void)

{function_declarations}
