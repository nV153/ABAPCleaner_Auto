*&---------------------------------------------------------------------*
*& Report z_test1
*&---------------------------------------------------------------------*
*&
*&---------------------------------------------------------------------*
REPORT z_test1.

TABLES sflight.

TYPES: BEGIN OF ty_out,
         carrid TYPE sflight-carrid,
         connid TYPE sflight-connid,
         fldate TYPE sflight-fldate,
         seats  TYPE i,
       END OF ty_out.

DATA gt_out         TYPE STANDARD TABLE OF ty_out WITH DEFAULT KEY.
DATA gs_out         TYPE ty_out.
DATA gt_sflight     LIKE sflight OCCURS 0.
DATA gs_sflight     LIKE sflight.
DATA lv_cnt         TYPE i.
DATA lv_text        TYPE string.
DATA lv_dummy       TYPE i.
DATA lv_useless     TYPE p LENGTH 8 DECIMALS 0.
DATA lv_moreUseless TYPE string.

PARAMETERS p_carr TYPE sflight-carrid DEFAULT 'LH'.

START-OF-SELECTION.
  CLEAR gt_out.
  CLEAR gs_out.
  CLEAR gt_sflight.
  CLEAR gs_sflight.
  CLEAR lv_cnt.
  CLEAR lv_text.
  CLEAR lv_dummy.

  SELECT * FROM sflight INTO TABLE gt_sflight WHERE carrid = p_carr.
  IF sy-subrc <> 0.
    WRITE / 'No data'.
    RETURN.
  ENDIF.

  LOOP AT gt_sflight INTO gs_sflight.
    lv_dummy = 0.
    lv_dummy = lv_dummy + 1.

    IF gs_sflight-seatsocc > 0.
      gs_out-carrid = gs_sflight-carrid.
      gs_out-connid = gs_sflight-connid.
      gs_out-fldate = gs_sflight-fldate.
      gs_out-seats  = gs_sflight-seatsocc.

      APPEND gs_out TO gt_out.
      CLEAR gs_out.
    ELSE.
      CONTINUE.
    ENDIF.
  ENDLOOP.

  SORT gt_out BY carrid
                 connid
                 fldate.
  DELETE ADJACENT DUPLICATES FROM gt_out COMPARING carrid connid fldate.

  DESCRIBE TABLE gt_out LINES lv_cnt.
  CONCATENATE 'Records:' '123' INTO lv_text SEPARATED BY space.
  WRITE / lv_text.

  ULINE.

  LOOP AT gt_out INTO gs_out.
    WRITE: / gs_out-carrid, gs_out-connid, gs_out-fldate, gs_out-seats.
  ENDLOOP.

  PERFORM do_more_stuff USING gt_out[].

FORM do_more_stuff USING it_data TYPE STANDARD TABLE.
  DATA lv_lines TYPE i.
  DATA lv_idx   TYPE i.
  " TODO: variable is assigned but never used (ABAP cleaner)
  DATA ls_any   TYPE REF TO data.

  FIELD-SYMBOLS <row> TYPE any.

  lv_lines = lines( it_data ).
  IF lv_lines = 0.
    WRITE / 'Empty'.
  ELSE.
    DO lv_lines TIMES.
      lv_idx = sy-index.
      ASSIGN it_data[ lv_idx ] TO <row>.
      IF sy-subrc = 0.
        CREATE DATA ls_any LIKE <row>.
        FREE ls_any.
      ENDIF.
    ENDDO.
  ENDIF.
ENDFORM.