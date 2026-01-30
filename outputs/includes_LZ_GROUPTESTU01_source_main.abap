FUNCTION z_moduletest.
*"----------------------------------------------------------------------
*"*"Local Interface:
*"----------------------------------------------------------------------
  " You can use the template 'functionModuleParameter' to add here the signature!

  SELECT * FROM sflight
  " TODO: variable is assigned but never used (ABAP cleaner)
    INTO TABLE @DATA(lv_test).
ENDFUNCTION.